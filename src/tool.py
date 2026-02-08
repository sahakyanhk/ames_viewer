# vim: set expandtab shiftwidth=4 softtabstop=4:

import glob
import os
import re

from chimerax.core.tools import ToolInstance
from chimerax.ui import MainToolWindow

from Qt.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QWidget, QPushButton,
    QSlider, QLabel, QSpinBox, QGroupBox,
    QComboBox, QCheckBox, QFileDialog, QButtonGroup
)
from Qt.QtCore import Qt, QTimer


def sorted_alphanumeric(data):
    """Sort filenames alphanumerically by basename."""
    convert = lambda text: int(text) if text.isdigit() else text.lower()
    alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', os.path.basename(key))]
    return sorted(data, key=alphanum_key)


class AMESViewerTool(ToolInstance):
    """Tool for visualizing AMES evolutionary trajectories."""

    SESSION_ENDURING = False
    SESSION_SAVE = False
    help = "help:user/tools/amesviewer.html"

    def __init__(self, session, tool_name):
        super().__init__(session, tool_name)
        
        self.display_name = "AMES Trajectory Viewer"
        self.structures = []  # List of model IDs in trajectory order
        self.pending_files = []  # Files selected but not yet loaded
        self.current_frame = 0
        self.is_playing = False
        self.play_speed = 100  # milliseconds between frames (10 fps)
        self.is_recording = False  # Flag to stop recording
        self.tmp_dir = None  # Temporary directory for USalign output
        self.movie_filepath = None  # Path for movie encoding
        self.record_all_mode = False  # Interactive recording mode
        
        # Timer for animation
        self.timer = QTimer()
        self.timer.timeout.connect(self._advance_frame)
        
        # Build the GUI
        self.tool_window = MainToolWindow(self)
        self._build_ui()
        self.tool_window.manage(placement="side")

    def _build_ui(self):
        """Build the tool's user interface."""
        parent = self.tool_window.ui_area
        main_layout = QVBoxLayout()
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(6, 6, 6, 6)
        parent.setLayout(main_layout)

        # === Row 1: Load + Alignment side by side (equal width) ===
        row1_layout = QHBoxLayout()
        row1_layout.setSpacing(4)

        # Load Section
        load_group = QGroupBox("Load Trajectory")
        load_layout = QVBoxLayout()
        load_layout.setSpacing(4)
        load_layout.setContentsMargins(6, 6, 6, 6)
        load_group.setLayout(load_layout)
        
        select_btns_layout = QHBoxLayout()
        self.select_files_btn = QPushButton("Files...")
        self.select_files_btn.clicked.connect(self._select_files)
        self.select_files_btn.setToolTip("Select PDB files")
        select_btns_layout.addWidget(self.select_files_btn)

        self.select_folder_btn = QPushButton("Folder...")
        self.select_folder_btn.clicked.connect(self._select_folder)
        self.select_folder_btn.setToolTip("Select folder with PDB files")
        select_btns_layout.addWidget(self.select_folder_btn)

        self.run_load_btn = QPushButton("Load")
        self.run_load_btn.clicked.connect(self._run_load)
        self.run_load_btn.setToolTip("Load selected files")
        self.run_load_btn.setEnabled(False)
        select_btns_layout.addWidget(self.run_load_btn)
        load_layout.addLayout(select_btns_layout)

        self.load_status = QLabel("No files selected")
        load_layout.addWidget(self.load_status)

        usalign_layout = QHBoxLayout()
        self.usalign_check = QCheckBox("Align with USalign")
        self.usalign_check.setChecked(False)
        self.usalign_check.setToolTip("Pre-align structures using USalign before loading")
        usalign_layout.addWidget(self.usalign_check)
        usalign_layout.addStretch()
        load_layout.addLayout(usalign_layout)

        load_skip_layout = QHBoxLayout()
        load_skip_layout.addWidget(QLabel("Load every:"))
        self.load_skip_spin = QSpinBox()
        self.load_skip_spin.setMinimum(1)
        self.load_skip_spin.setMaximum(100)
        self.load_skip_spin.setValue(1)
        self.load_skip_spin.setToolTip("Load every Nth file (1=all, 2=every 2nd, etc.)")
        self.load_skip_spin.setMaximumWidth(50)
        load_skip_layout.addWidget(self.load_skip_spin)
        load_skip_layout.addStretch()
        load_layout.addLayout(load_skip_layout)

        row1_layout.addWidget(load_group, 1)  # stretch factor 1

        # Alignment Section
        align_group = QGroupBox("Align structures by chain")
        align_layout = QVBoxLayout()
        align_layout.setSpacing(4)
        align_layout.setContentsMargins(6, 6, 6, 6)
        align_group.setLayout(align_layout)
        
        chain_layout = QHBoxLayout()
        chain_layout.addWidget(QLabel("Chain:"))
        self.chain_combo = QComboBox()
        self.chain_combo.addItems(["A", "B"])
        chain_layout.addWidget(self.chain_combo)
        chain_layout.addStretch()
        align_layout.addLayout(chain_layout)
        
        self.align_btn = QPushButton("Align Sequentially")
        self.align_btn.clicked.connect(self._align_structures)
        self.align_btn.setEnabled(False)
        align_layout.addWidget(self.align_btn)
        
        self.align_status = QLabel("Not aligned")
        align_layout.addWidget(self.align_status)

        row1_layout.addWidget(align_group, 1)  # stretch factor 1
        main_layout.addLayout(row1_layout)

        # === Playback Section ===
        play_group = QGroupBox("Playback")
        play_layout = QVBoxLayout()
        play_layout.setSpacing(4)
        play_layout.setContentsMargins(6, 6, 6, 6)
        play_group.setLayout(play_layout)

        # Frame slider
        slider_layout = QHBoxLayout()
        slider_layout.addWidget(QLabel("Frame:"))
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setMinimum(0)
        self.frame_slider.setMaximum(0)
        self.frame_slider.setValue(0)
        self.frame_slider.valueChanged.connect(self._on_slider_changed)
        self.frame_slider.setEnabled(False)
        slider_layout.addWidget(self.frame_slider)
        
        self.frame_label = QLabel("0 / 0")
        self.frame_label.setMinimumWidth(50)
        slider_layout.addWidget(self.frame_label)
        play_layout.addLayout(slider_layout)

        # Speed slider (fps) - above playback buttons
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("fps:"))
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setMinimum(1)
        self.speed_slider.setMaximum(30)
        self.speed_slider.setMaximumWidth(120)
        self.speed_slider.setToolTip("Frames per second for playback and movie recording")
        speed_layout.addWidget(self.speed_slider)
        self.speed_label = QLabel("10")
        self.speed_label.setMinimumWidth(20)
        speed_layout.addWidget(self.speed_label)
        speed_layout.addStretch()
        # Set value after label exists so signal updates it correctly
        self.speed_slider.setValue(10)
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        play_layout.addLayout(speed_layout)

        # Playback controls
        controls_layout = QHBoxLayout()

        self.first_btn = QPushButton("|<")
        self.first_btn.clicked.connect(self._go_first)
        self.first_btn.setEnabled(False)
        self.first_btn.setMaximumWidth(28)
        controls_layout.addWidget(self.first_btn)

        self.prev_btn = QPushButton("<")
        self.prev_btn.clicked.connect(self._go_prev)
        self.prev_btn.setEnabled(False)
        self.prev_btn.setMaximumWidth(28)
        controls_layout.addWidget(self.prev_btn)

        self.play_btn = QPushButton("Play")
        self.play_btn.clicked.connect(self._toggle_play)
        self.play_btn.setEnabled(False)
        self.play_btn.setMaximumWidth(38)
        controls_layout.addWidget(self.play_btn)

        self.next_btn = QPushButton(">")
        self.next_btn.clicked.connect(self._go_next)
        self.next_btn.setEnabled(False)
        self.next_btn.setMaximumWidth(28)
        controls_layout.addWidget(self.next_btn)

        self.last_btn = QPushButton(">|")
        self.last_btn.clicked.connect(self._go_last)
        self.last_btn.setEnabled(False)
        self.last_btn.setMaximumWidth(28)
        controls_layout.addWidget(self.last_btn)

        controls_layout.addWidget(QLabel("Skip:"))
        self.skip_spin = QSpinBox()
        self.skip_spin.setMinimum(1)
        self.skip_spin.setMaximum(100)
        self.skip_spin.setValue(1)
        self.skip_spin.setToolTip("Show every Nth frame (1=all frames)")
        self.skip_spin.setMaximumWidth(45)
        controls_layout.addWidget(self.skip_spin)

        self.loop_check = QCheckBox("Loop")
        self.loop_check.setChecked(False)
        controls_layout.addWidget(self.loop_check)

        controls_layout.addStretch()
        play_layout.addLayout(controls_layout)

        main_layout.addWidget(play_group)

        # === Row 2: Display + Movie side by side (equal width) ===
        row2_layout = QHBoxLayout()
        row2_layout.setSpacing(4)

        # Display Section
        display_group = QGroupBox("Display")
        display_layout = QVBoxLayout()
        display_layout.setSpacing(4)
        display_layout.setContentsMargins(6, 6, 6, 6)
        display_group.setLayout(display_layout)
        
        # Widths for alignment
        label_width = 50
        check_width = 75

        # Chain A styles
        chainA_layout = QHBoxLayout()
        labelA = QLabel("Chain A:")
        labelA.setFixedWidth(label_width)
        chainA_layout.addWidget(labelA)
        self.cartoon_check_A = QCheckBox("Cartoon")
        self.cartoon_check_A.setFixedWidth(check_width)
        self.cartoon_check_A.setChecked(True)
        self.cartoon_check_A.stateChanged.connect(self._on_style_changed)
        chainA_layout.addWidget(self.cartoon_check_A)
        self.stick_check_A = QCheckBox("Stick")
        self.stick_check_A.setFixedWidth(check_width)
        self.stick_check_A.stateChanged.connect(self._on_style_changed)
        chainA_layout.addWidget(self.stick_check_A)
        self.sphere_check_A = QCheckBox("Sphere")
        self.sphere_check_A.setFixedWidth(check_width)
        self.sphere_check_A.stateChanged.connect(self._on_style_changed)
        chainA_layout.addWidget(self.sphere_check_A)
        chainA_layout.addStretch()
        display_layout.addLayout(chainA_layout)

        # Chain B styles
        chainB_layout = QHBoxLayout()
        labelB = QLabel("Chain B:")
        labelB.setFixedWidth(label_width)
        chainB_layout.addWidget(labelB)
        self.cartoon_check_B = QCheckBox("Cartoon")
        self.cartoon_check_B.setFixedWidth(check_width)
        self.cartoon_check_B.stateChanged.connect(self._on_style_changed)
        chainB_layout.addWidget(self.cartoon_check_B)
        self.stick_check_B = QCheckBox("Stick")
        self.stick_check_B.setFixedWidth(check_width)
        self.stick_check_B.stateChanged.connect(self._on_style_changed)
        chainB_layout.addWidget(self.stick_check_B)
        self.sphere_check_B = QCheckBox("Sphere")
        self.sphere_check_B.setFixedWidth(check_width)
        self.sphere_check_B.stateChanged.connect(self._on_style_changed)
        chainB_layout.addWidget(self.sphere_check_B)
        chainB_layout.addStretch()
        display_layout.addLayout(chainB_layout)

        # Ligands/Ions styles
        ligand_layout = QHBoxLayout()
        labelLig = QLabel("Ligand:")
        labelLig.setFixedWidth(label_width)
        ligand_layout.addWidget(labelLig)
        self.ball_check_lig = QCheckBox("Ball")
        self.ball_check_lig.setFixedWidth(check_width)
        self.ball_check_lig.setToolTip("Ball & Stick style")
        self.ball_check_lig.stateChanged.connect(self._on_ligand_changed)
        ligand_layout.addWidget(self.ball_check_lig)
        self.stick_check_lig = QCheckBox("Stick")
        self.stick_check_lig.setFixedWidth(check_width)
        self.stick_check_lig.stateChanged.connect(self._on_ligand_changed)
        ligand_layout.addWidget(self.stick_check_lig)
        self.sphere_check_lig = QCheckBox("Sphere")
        self.sphere_check_lig.setFixedWidth(check_width)
        self.sphere_check_lig.stateChanged.connect(self._on_ligand_changed)
        ligand_layout.addWidget(self.sphere_check_lig)
        ligand_layout.addStretch()
        display_layout.addLayout(ligand_layout)

        # Coloring
        color_layout = QHBoxLayout()
        labelColor = QLabel("Color:")
        labelColor.setFixedWidth(label_width)
        color_layout.addWidget(labelColor)
        self.color_combo = QComboBox()
        self.color_combo.addItems(["By Chain", "By pLDDT", "By Secondary Structure", "Rainbow", "By Atom"])
        self.color_combo.setCurrentText("By pLDDT")
        self.color_combo.currentTextChanged.connect(self._on_color_changed)
        color_layout.addWidget(self.color_combo)
        color_layout.addStretch()
        display_layout.addLayout(color_layout)

        row2_layout.addWidget(display_group, 1)  # stretch factor 1
        
        # Movie Section
        movie_group = QGroupBox("Movie")
        movie_layout = QVBoxLayout()
        movie_layout.setSpacing(4)
        movie_layout.setContentsMargins(6, 6, 6, 6)
        movie_group.setLayout(movie_layout)

        # Mutually exclusive recording mode checkboxes
        self.movie_mode_group = QButtonGroup(self.tool_window.ui_area)
        self.movie_mode_group.setExclusive(False)

        self.record_traj_check = QCheckBox("Record trajectory")
        self.record_traj_check.setChecked(True)
        self.record_traj_check.setToolTip("Record trajectory frame-by-frame at playback fps")
        self.movie_mode_group.addButton(self.record_traj_check)

        self.record_all_check = QCheckBox("Record user actions")
        self.record_all_check.setChecked(False)
        self.record_all_check.setToolTip("Record user actions on screen until Stop is clicked")
        self.movie_mode_group.addButton(self.record_all_check)

        self.fixed_duration_check = QCheckBox("Fixed duration:")
        self.fixed_duration_check.setChecked(False)
        self.fixed_duration_check.setToolTip("Record trajectory fitted to a target duration")
        self.movie_mode_group.addButton(self.fixed_duration_check)

        self.duration_spin = QSpinBox()
        self.duration_spin.setMinimum(1)
        self.duration_spin.setMaximum(300)
        self.duration_spin.setValue(10)
        self.duration_spin.setSuffix("s")
        self.duration_spin.setEnabled(False)
        self.duration_spin.setToolTip("Target movie duration in seconds")
        self.duration_spin.setMaximumWidth(60)

        # Each row in its own HBoxLayout for consistent alignment
        for check in (self.record_traj_check, self.record_all_check):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(check)
            row.addStretch()
            movie_layout.addLayout(row)

        duration_layout = QHBoxLayout()
        duration_layout.setContentsMargins(0, 0, 0, 0)
        duration_layout.addWidget(self.fixed_duration_check)
        duration_layout.addWidget(self.duration_spin)
        duration_layout.addStretch()
        movie_layout.addLayout(duration_layout)

        self.movie_mode_group.buttonClicked.connect(self._on_movie_mode_changed)

        # Resolution option
        res_layout = QHBoxLayout()
        res_layout.setContentsMargins(0, 0, 0, 0)
        res_layout.addWidget(QLabel("Size:"))
        self.res_width_spin = QSpinBox()
        self.res_width_spin.setMinimum(0)
        self.res_width_spin.setMaximum(7680)
        self.res_width_spin.setValue(0)
        self.res_width_spin.setSpecialValueText("auto")
        self.res_width_spin.setToolTip("Frame width (0 = window resolution)")
        self.res_width_spin.setMaximumWidth(65)
        res_layout.addWidget(self.res_width_spin)
        res_layout.addWidget(QLabel("x"))
        self.res_height_spin = QSpinBox()
        self.res_height_spin.setMinimum(0)
        self.res_height_spin.setMaximum(4320)
        self.res_height_spin.setValue(0)
        self.res_height_spin.setSpecialValueText("auto")
        self.res_height_spin.setToolTip("Frame height (0 = window resolution)")
        self.res_height_spin.setMaximumWidth(65)
        res_layout.addWidget(self.res_height_spin)
        res_layout.addStretch()
        movie_layout.addLayout(res_layout)

        # Record/Stop buttons
        movie_btns_layout = QHBoxLayout()
        self.record_btn = QPushButton("Record")
        self.record_btn.clicked.connect(self._record_movie)
        movie_btns_layout.addWidget(self.record_btn)

        self.stop_record_btn = QPushButton("Stop")
        self.stop_record_btn.clicked.connect(self._stop_recording)
        self.stop_record_btn.setEnabled(False)
        movie_btns_layout.addWidget(self.stop_record_btn)
        movie_btns_layout.addStretch()
        movie_layout.addLayout(movie_btns_layout)

        self.movie_status = QLabel("")
        movie_layout.addWidget(self.movie_status)

        row2_layout.addWidget(movie_group, 1)  # stretch factor 1
        
        main_layout.addLayout(row2_layout)
        
        # Info label
        self.info_label = QLabel("")
        main_layout.addWidget(self.info_label)

    def _select_files(self):
        """Select PDB files (does not load yet)."""
        filepaths, _ = QFileDialog.getOpenFileNames(
            self.tool_window.ui_area,
            "Select PDB Files",
            "",
            "PDB Files (*.pdb *.cif);;All Files (*)"
        )

        if filepaths:
            self.pending_files = sorted_alphanumeric(filepaths)
            self._update_pending_status()

    def _select_folder(self):
        """Select folder with PDB files (does not load yet)."""
        directory = QFileDialog.getExistingDirectory(
            self.tool_window.ui_area,
            "Select Folder with PDB Files"
        )

        if not directory:
            return

        # Find all PDB and CIF files in the folder
        pdb_files = glob.glob(os.path.join(directory, "*.pdb"))
        cif_files = glob.glob(os.path.join(directory, "*.cif"))
        filepaths = pdb_files + cif_files

        if filepaths:
            self.pending_files = sorted_alphanumeric(filepaths)
            self._update_pending_status()
        else:
            self.pending_files = []
            self.load_status.setText("No PDB files found")
            self.run_load_btn.setEnabled(False)
            self.session.logger.warning(f"No PDB/CIF files found in {directory}")

    def _update_pending_status(self):
        """Update status label and Load button based on pending files."""
        n = len(self.pending_files)
        if n == 0:
            self.load_status.setText("No files selected")
            self.run_load_btn.setEnabled(False)
        elif n == 1:
            self.load_status.setText("1 file selected (need >= 2)")
            self.run_load_btn.setEnabled(False)
        else:
            self.load_status.setText(f"{n} files selected")
            self.run_load_btn.setEnabled(True)

    def _validate_structures(self):
        """Remove deleted models from structures list. Returns True if structures remain."""
        before = len(self.structures)
        self.structures = [m for m in self.structures if not m.deleted]
        after = len(self.structures)

        if before != after:
            if after == 0:
                self._reset_ui()
                return False
            # Update slider range for remaining structures
            self.frame_slider.setMaximum(after - 1)
            if self.current_frame >= after:
                self.current_frame = after - 1

        return after > 0

    def _reset_ui(self):
        """Reset UI to initial state (no structures loaded)."""
        self._stop_playback()
        self.frame_slider.setMaximum(0)
        self.frame_slider.setValue(0)
        self.frame_slider.setEnabled(False)
        self.frame_label.setText("0 / 0")
        self.align_btn.setEnabled(False)
        self.play_btn.setEnabled(False)
        self.first_btn.setEnabled(False)
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.last_btn.setEnabled(False)
        self.record_btn.setEnabled(False)
        self.info_label.setText("")

    def _model_spec(self):
        """Return ChimeraX model specifier for all tool structures."""
        if not self.structures:
            return ""
        return "#" + ",".join(m.id_string for m in self.structures)

    def _run_load(self):
        """Load the pending files."""
        if self.pending_files:
            self._load_files(self.pending_files)

    def _load_files(self, filepaths):
        """Common method to load a list of PDB files."""
        if len(filepaths) < 2:
            self.session.logger.warning("Please select at least 2 structures")
            self.load_status.setText("Need >= 2 files")
            return
        
        # Sort filepaths alphanumerically by filename
        filepaths = sorted_alphanumeric(filepaths)

        # Close any previously loaded structures from this tool
        self._close_structures()
        self._cleanup_tmp()

        # Apply load skip (load every Nth file) before alignment
        files_to_load = filepaths
        load_skip = self.load_skip_spin.value()
        if load_skip > 1:
            files_to_load = files_to_load[::load_skip]
            self.session.logger.info(f"Using every {load_skip} file ({len(files_to_load)} files)")

        if len(files_to_load) < 2:
            self.session.logger.warning("Need at least 2 structures after skipping")
            self.load_status.setText("Need >= 2 files")
            return

        # Pre-align with USalign if checkbox is checked
        if self.usalign_check.isChecked():
            self.load_status.setText("Pre-aligning with USalign...")
            self.session.ui.processEvents()
            aligned_files = self._align_with_usalign(files_to_load)
            if aligned_files is None:
                self.load_status.setText("USalign failed")
                return
            files_to_load = aligned_files

        self.load_status.setText("Loading...")
        self.session.ui.processEvents()

        from chimerax.core.commands import run
        from chimerax.atomic import AtomicStructure

        # Load files and maintain order
        self.structures = []
        n_files = len(files_to_load)

        for i, filepath in enumerate(files_to_load):
            filename = os.path.basename(filepath)
            try:
                # Get models before opening
                models_before = set(self.session.models.list(type=AtomicStructure))
                
                # Open the file - try to get return value
                result = run(self.session, f'open "{filepath}"', log=False)
                
                # Try to get model from return value first
                model = None
                if result is not None:
                    if isinstance(result, (list, tuple)) and len(result) > 0:
                        # result might be (models, status) or just models
                        first = result[0]
                        if isinstance(first, (list, tuple)) and len(first) > 0:
                            model = first[0]
                        elif isinstance(first, AtomicStructure):
                            model = first
                
                # If that didn't work, find new model by comparing
                if model is None:
                    models_after = set(self.session.models.list(type=AtomicStructure))
                    new_models = models_after - models_before
                    if new_models:
                        model = list(new_models)[0]
                
                if model is not None:
                    # Hide immediately
                    model.display = False
                    self.structures.append(model)
                    self.session.logger.info(f"Loaded {filename} as frame {i+1}")
                else:
                    self.session.logger.warning(f"Could not capture model from {filename}")
                    
            except Exception as e:
                self.session.logger.warning(f"Failed to load {filename}: {e}")
            
            self.load_status.setText(f"Loading {i+1}/{n_files}")
            self.session.ui.processEvents()
        
        if len(self.structures) < 2:
            self.session.logger.warning("Need at least 2 structures loaded")
            self.load_status.setText("Error: Need >= 2")
            return
        
        # Hide all structures after loading
        for model in self.structures:
            model.display = False
        
        self.load_status.setText(f"{len(self.structures)} loaded")
        self._setup_trajectory()

        # Clean up temporary USalign files after loading
        self._cleanup_tmp()

    def _find_usalign(self):
        """Find USalign executable in common locations."""
        import shutil as sh

        # First check if it's in PATH
        usalign = sh.which("USalign")
        if usalign:
            return usalign

        # Common conda/miniforge locations
        home = os.path.expanduser("~")
        common_paths = [
            os.path.join(home, "miniforge3", "bin", "USalign"),
            os.path.join(home, "miniconda3", "bin", "USalign"),
            os.path.join(home, "anaconda3", "bin", "USalign"),
            os.path.join(home, "conda", "bin", "USalign"),
            "/usr/local/bin/USalign",
            "/opt/homebrew/bin/USalign",
        ]

        for path in common_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path

        return None

    def _align_with_usalign(self, filepaths):
        """Pre-align structures using USalign before loading."""
        import tempfile
        import shutil
        import subprocess

        # Find USalign executable
        usalign_path = self._find_usalign()
        if not usalign_path:
            self.session.logger.error(
                "USalign not found. Please install USalign or add it to PATH.\n"
                "Searched: PATH, ~/miniforge3/bin, ~/miniconda3/bin, ~/anaconda3/bin"
            )
            return None

        self.tmp_dir = tempfile.mkdtemp(prefix="ames_usalign_")
        aligned_files = []
        prev_pdb = None

        n_files = len(filepaths)
        for i, filepath in enumerate(filepaths):
            filename = os.path.basename(filepath)
            output_path = os.path.join(self.tmp_dir, filename)

            if prev_pdb is None:
                # First file: just copy as-is
                shutil.copy(filepath, output_path)
            else:
                # Align current to previous using USalign
                # USalign -chimerax prefix creates: prefix.pdb + .cxc script files
                name_no_ext = os.path.splitext(filename)[0]
                prefix = os.path.join(self.tmp_dir, name_no_ext)
                try:
                    result = subprocess.run(
                        [usalign_path, filepath, prev_pdb, "-mm", "1", "-chimerax", prefix],
                        capture_output=True,
                        text=True
                    )
                    # Output is prefix.pdb
                    usalign_output = f"{prefix}.pdb"
                    if result.returncode == 0 and os.path.exists(usalign_output):
                        output_path = usalign_output  # Use the aligned file
                    else:
                        self.session.logger.warning(f"USalign failed for {filename}: {result.stderr}")
                        shutil.copy(filepath, output_path)
                except Exception as e:
                    self.session.logger.warning(f"USalign error for {filename}: {e}")
                    shutil.copy(filepath, output_path)

            aligned_files.append(output_path)
            prev_pdb = output_path  # Align to the aligned previous file

            self.load_status.setText(f"Aligning {i+1}/{n_files}")
            self.session.ui.processEvents()

        # Remove .cxc script files created by USalign (keep only .pdb files)
        for f in os.listdir(self.tmp_dir):
            if f.endswith(".cxc"):
                try:
                    os.remove(os.path.join(self.tmp_dir, f))
                except Exception:
                    pass

        return aligned_files

    def _cleanup_tmp(self):
        """Clean up temporary directory used for USalign output."""
        if self.tmp_dir and os.path.exists(self.tmp_dir):
            import shutil
            try:
                shutil.rmtree(self.tmp_dir)
            except Exception as e:
                self.session.logger.warning(f"Failed to cleanup tmp dir: {e}")
            self.tmp_dir = None

    def _setup_trajectory(self):
        """Setup trajectory after structures are loaded."""
        n = len(self.structures)
        if n == 0:
            return
        
        # Update UI
        self.frame_slider.setMaximum(n - 1)
        self.frame_slider.setValue(0)
        self.frame_slider.setEnabled(True)
        self._update_frame_label()
        
        # Enable buttons
        self.align_btn.setEnabled(True)
        self.play_btn.setEnabled(True)
        self.first_btn.setEnabled(True)
        self.prev_btn.setEnabled(True)
        self.next_btn.setEnabled(True)
        self.last_btn.setEnabled(True)
        self.record_btn.setEnabled(True)
        
        self.align_status.setText("Not aligned")
        
        # Apply display settings to all structures at once
        self._apply_styles()
        self._apply_coloring()
        self._apply_ligand_style()

        # Show first frame, hide others
        self.current_frame = 0
        self._show_frame(0)

    def _align_structures(self):
        """Sequentially align all structures using matchmaker."""
        if not self._validate_structures() or len(self.structures) < 2:
            return
        
        from chimerax.core.commands import run
        
        # Get selected chain
        chain = self.chain_combo.currentText()
        
        self.align_status.setText("Aligning...")
        self.session.ui.processEvents()  # Update UI
        
        n = len(self.structures)
        for i in range(1, n):
            # Get model IDs
            prev_model = self.structures[i - 1]
            curr_model = self.structures[i]
            
            # Get the model specifier strings with chain
            prev_spec = f"#{prev_model.id_string}/{chain}"
            curr_spec = f"#{curr_model.id_string}/{chain}"
            
            # Run matchmaker: align current to previous
            try:
                run(self.session, f"matchmaker {curr_spec} to {prev_spec}")
                self.session.logger.info(
                    f"Aligned {curr_spec} to {prev_spec} ({i}/{n-1})"
                )
            except Exception as e:
                self.session.logger.warning(
                    f"Failed to align {curr_spec} to {prev_spec}: {e}"
                )
            
            # Update progress
            self.align_status.setText(f"Aligning... {i}/{n-1}")
            self.session.ui.processEvents()
        
        self.align_status.setText(f"Aligned (chain {chain})")
        self.session.logger.info("Sequential alignment complete")

    def _show_frame(self, frame_idx):
        """Show only the specified frame, hide all others."""
        if not self._validate_structures():
            return

        frame_idx = max(0, min(frame_idx, len(self.structures) - 1))
        self.current_frame = frame_idx

        # Hide all structures, show only current
        for i, model in enumerate(self.structures):
            model.display = (i == frame_idx)

        # Update UI
        self.frame_slider.blockSignals(True)
        self.frame_slider.setValue(frame_idx)
        self.frame_slider.blockSignals(False)
        self._update_frame_label()

        # Update info
        model = self.structures[frame_idx]
        n_atoms = model.num_atoms
        n_residues = model.num_residues
        self.info_label.setText(
            f"Model: #{model.id_string} | "
            f"Residues: {n_residues} | Atoms: {n_atoms}"
        )

    def _update_frame_label(self):
        """Update the frame counter label."""
        n = len(self.structures)
        self.frame_label.setText(f"{self.current_frame + 1} / {n}")

    def _on_slider_changed(self, value):
        """Handle slider value change."""
        self._show_frame(value)

    def _go_first(self):
        """Go to first frame."""
        self._show_frame(0)

    def _go_last(self):
        """Go to last frame."""
        self._show_frame(len(self.structures) - 1)

    def _go_prev(self):
        """Go to previous frame (respects skip setting)."""
        skip = self.skip_spin.value()
        new_frame = self.current_frame - skip
        if new_frame < 0:
            if self.loop_check.isChecked():
                new_frame = len(self.structures) - 1
            else:
                new_frame = 0
        self._show_frame(new_frame)

    def _go_next(self):
        """Go to next frame (respects skip setting)."""
        skip = self.skip_spin.value()
        new_frame = self.current_frame + skip
        if new_frame < len(self.structures):
            self._show_frame(new_frame)
        elif self.loop_check.isChecked():
            self._show_frame(0)

    def _toggle_play(self):
        """Toggle playback."""
        if self.is_playing:
            self._stop_playback()
        else:
            self._start_playback()

    def _start_playback(self):
        """Start animation playback."""
        self.is_playing = True
        self.play_btn.setText("Stop")
        self.timer.start(self.play_speed)

    def _stop_playback(self):
        """Stop animation playback."""
        self.is_playing = False
        self.play_btn.setText("Play")
        self.timer.stop()

    def _advance_frame(self):
        """Advance to next frame (called by timer, respects skip setting)."""
        if not self._validate_structures():
            self._stop_playback()
            return
        skip = self.skip_spin.value()
        new_frame = self.current_frame + skip
        if new_frame < len(self.structures):
            self._show_frame(new_frame)
        elif self.loop_check.isChecked():
            self._show_frame(0)
        else:
            self._stop_playback()

    def _on_speed_changed(self, value):
        """Handle speed slider change (fps)."""
        # Convert fps to ms per frame
        self.play_speed = int(1000 / value)
        self.speed_label.setText(str(value))
        if self.is_playing:
            self.timer.setInterval(self.play_speed)

    def _on_movie_mode_changed(self, clicked_btn):
        """Ensure only one movie mode checkbox is selected at a time."""
        if clicked_btn.isChecked():
            for btn in self.movie_mode_group.buttons():
                if btn is not clicked_btn:
                    btn.setChecked(False)
        self.duration_spin.setEnabled(self.fixed_duration_check.isChecked())

    def _on_style_changed(self, state=None):
        """Handle style checkbox changes."""
        self._apply_styles()

    def _on_color_changed(self, color_mode):
        """Handle color dropdown changes."""
        self._apply_coloring()

    def _on_ligand_changed(self, state=None):
        """Handle ligand checkbox or style changes."""
        self._apply_ligand_style()

    def _apply_styles(self):
        """Apply display styles to tool structures only."""
        if not self._validate_structures():
            return

        from chimerax.core.commands import run
        spec = self._model_spec()

        try:
            # Chain A
            run(self.session, f"hide {spec}/A target ac", log=False)
            if self.cartoon_check_A.isChecked():
                run(self.session, f"cartoon {spec}/A", log=False)
                run(self.session, f"show {spec}/A target c", log=False)
            if self.stick_check_A.isChecked():
                run(self.session, f"show {spec}/A target a", log=False)
                run(self.session, f"style {spec}/A stick", log=False)
            if self.sphere_check_A.isChecked():
                run(self.session, f"show {spec}/A target a", log=False)
                run(self.session, f"style {spec}/A sphere", log=False)
        except Exception as e:
            self.session.logger.warning(f"Chain A style error: {e}")

        try:
            # Chain B
            run(self.session, f"hide {spec}/B target ac", log=False)
            if self.cartoon_check_B.isChecked():
                run(self.session, f"cartoon {spec}/B", log=False)
                run(self.session, f"show {spec}/B target c", log=False)
            if self.stick_check_B.isChecked():
                run(self.session, f"show {spec}/B target a", log=False)
                run(self.session, f"style {spec}/B stick", log=False)
            if self.sphere_check_B.isChecked():
                run(self.session, f"show {spec}/B target a", log=False)
                run(self.session, f"style {spec}/B sphere", log=False)
        except Exception as e:
            self.session.logger.warning(f"Chain B style error: {e}")

    def _apply_coloring(self):
        """Apply coloring to tool structures only."""
        if not self._validate_structures():
            return

        from chimerax.core.commands import run
        spec = self._model_spec()

        color_mode = self.color_combo.currentText()

        try:
            if color_mode == "By Chain":
                run(self.session, f"color bychain {spec}", log=False)
            elif color_mode == "By pLDDT":
                run(self.session, f"color bfactor {spec} palette alphafold", log=False)
            elif color_mode == "By Secondary Structure":
                run(self.session, f"color helix {spec} purple", log=False)
                run(self.session, f"color strand {spec} yellow", log=False)
                run(self.session, f"color coil {spec} gray", log=False)
            elif color_mode == "Rainbow":
                run(self.session, f"rainbow {spec}", log=False)
            elif color_mode == "By Atom":
                run(self.session, f"color byhetero {spec}", log=False)
        except Exception as e:
            self.session.logger.warning(f"Coloring error: {e}")

    def _apply_ligand_style(self):
        """Apply ligand/ion display settings to tool structures only."""
        if not self._validate_structures():
            return

        from chimerax.core.commands import run
        lig_spec = f"{self._model_spec()} & ~protein & ~nucleic"

        show_stick = self.stick_check_lig.isChecked()
        show_sphere = self.sphere_check_lig.isChecked()
        show_ball = self.ball_check_lig.isChecked()
        show_any = show_stick or show_sphere or show_ball

        try:
            if show_any:
                run(self.session, f"show {lig_spec} target a", log=False)
                if show_ball:
                    run(self.session, f"style {lig_spec} ball", log=False)
                elif show_sphere:
                    run(self.session, f"style {lig_spec} sphere", log=False)
                elif show_stick:
                    run(self.session, f"style {lig_spec} stick", log=False)
            else:
                run(self.session, f"hide {lig_spec} target a", log=False)
        except Exception as e:
            self.session.logger.warning(f"Ligand style error: {e}")

    def _record_movie(self):
        """Record a movie of the trajectory playback."""
        from chimerax.core.commands import run

        # Get save path
        filepath, _ = QFileDialog.getSaveFileName(
            self.tool_window.ui_area,
            "Save Movie As",
            "trajectory.mp4",
            "MP4 Files (*.mp4);;All Files (*)"
        )

        if not filepath:
            return

        if not filepath.endswith('.mp4'):
            filepath += '.mp4'

        self.movie_filepath = filepath
        self.record_all_mode = self.record_all_check.isChecked()

        self.movie_status.setText("Recording...")
        self.record_btn.setEnabled(False)
        self.stop_record_btn.setEnabled(True)
        self.is_recording = True
        self.session.ui.processEvents()

        try:
            # Start recording
            record_cmd = "movie record"
            w = self.res_width_spin.value()
            h = self.res_height_spin.value()
            if w > 0 and h > 0:
                record_cmd += f" size {w},{h}"
            run(self.session, record_cmd)

            if self.record_all_mode:
                # Interactive mode: just start recording, user will stop manually
                self.movie_status.setText("Recording... (click Stop when done)")
                return  # Don't reset buttons, wait for stop

            # Frame-by-frame mode: play through trajectory
            if not self.structures:
                run(self.session, "movie abort")
                self.movie_status.setText("No structures loaded")
                self._finish_recording()
                return

            skip = self.skip_spin.value()
            frame_indices = list(range(0, len(self.structures), skip))
            n_frames = len(frame_indices)

            # Calculate framerate
            if self.fixed_duration_check.isChecked():
                target_duration = self.duration_spin.value()
                framerate = max(1, n_frames / target_duration)
            else:
                framerate = self.speed_slider.value()

            # Play through frames
            for idx, frame_i in enumerate(frame_indices):
                if not self.is_recording:
                    # Stopped by _stop_recording which already handled abort
                    break

                self._show_frame(frame_i)
                run(self.session, "wait 1")
                self.movie_status.setText(f"Recording {idx+1}/{n_frames}")
                self.session.ui.processEvents()

            # Encode if not stopped externally
            if self.is_recording:
                run(self.session, "movie stop")
                run(self.session, f'movie encode "{filepath}" framerate {framerate:.1f}')
                self.movie_status.setText(f"Saved: {os.path.basename(filepath)}")
                self.session.logger.info(f"Movie saved to {filepath} ({n_frames} frames, {framerate:.1f} fps)")
                self._finish_recording()
            # else: _stop_recording already called _finish_recording

        except Exception as e:
            self.session.logger.error(f"Movie recording failed: {e}")
            self.movie_status.setText(f"Error: {e}")
            try:
                run(self.session, "movie abort")
            except Exception:
                pass
            self._finish_recording()

    def _finish_recording(self):
        """Reset recording state."""
        self.is_recording = False
        self.record_all_mode = False
        self.record_btn.setEnabled(True)
        self.stop_record_btn.setEnabled(False)

    def _stop_recording(self):
        """Stop the movie recording."""
        from chimerax.core.commands import run

        self.is_recording = False
        self.movie_status.setText("Stopping...")

        if self.record_all_mode and self.movie_filepath:
            # Interactive mode: stop and encode now
            try:
                run(self.session, "movie stop")
                framerate = self.speed_slider.value()
                run(self.session, f'movie encode "{self.movie_filepath}" framerate {framerate:.1f}')
                self.movie_status.setText(f"Saved: {os.path.basename(self.movie_filepath)}")
                self.session.logger.info(f"Movie saved to {self.movie_filepath}")
            except Exception as e:
                self.session.logger.error(f"Movie encoding failed: {e}")
                self.movie_status.setText(f"Error: {e}")
                try:
                    run(self.session, "movie abort")
                except Exception:
                    pass
        else:
            # Frame-by-frame mode or no recording in progress - just abort
            try:
                run(self.session, "movie abort")
                self.movie_status.setText("Recording stopped")
            except Exception:
                pass

        self._finish_recording()

    def _close_structures(self):
        """Close all structures in our list with a single command."""
        if not self.structures:
            return

        from chimerax.core.commands import run

        spec = self._model_spec()
        try:
            run(self.session, f"close {spec}")
        except Exception:
            pass

        self.structures = []

    def delete(self):
        """Clean up when tool is closed."""
        self._stop_playback()
        self._close_structures()
        self._cleanup_tmp()
        super().delete()
