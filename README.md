# ChimeraX AMES Viewer

A ChimeraX tool for visualizing evolutionary trajectories from [AMES](https://github.com/sahakyanhk/ames) (Atomistic Molecular Evolution Simulator).

## Installation

### Option 1: Download Release (Easiest)

1. Download the latest `.whl` file from [Releases](../../releases)
2. In ChimeraX, run:
   ```
   toolshed install /path/to/ChimeraX_AMESViewer-0.1-py3-none-any.whl
   ```
3. Restart ChimeraX

### Option 2: Install from Source

```bash
git clone https://github.com/YOUR_USERNAME/ChimeraX_AMESViewer.git
cd ChimeraX_AMESViewer
make install
```

Or in ChimeraX:
```
devel install /path/to/ChimeraX_AMESViewer
```

## Usage

### Opening the Tool

1. Open ChimeraX
2. Go to **Tools > General > AMES Viewer**

### Load Trajectory

1. Click **Files...** or **Folder...** to select structures
2. Configure loading options:
   - **Align with USalign** - Pre-align structures before loading (requires USalign)
   - **Load every: N** - Skip files (1=all, 2=every 2nd, etc.)
3. Click **Load** to start loading

### Align Structures by Chain

- **Chain dropdown** - Select chain for alignment (A/B)
- **Align Sequentially** - Post-load alignment using ChimeraX matchmaker

### Playback

- **Frame slider** - Navigate through loaded structures
- **fps slider** (1-30, default 10) - Playback speed
- **|< < Play > >|** - Playback controls
- **Skip** - Show every Nth frame during playback
- **Loop** - Continuously loop the trajectory

### Display

| Row | Options | Default |
|-----|---------|---------|
| Chain A | Cartoon, Stick, Sphere | Cartoon on |
| Chain B | Cartoon, Stick, Sphere | All off |
| Ligand | Ball, Stick, Sphere | All off |
| Color | By Chain, By pLDDT, By Secondary Structure, Rainbow, By Atom | By pLDDT |

**Note:** Chain B defaults to off because it may be a ligand in some structures.

**Ligand** shows all non-protein/nucleic molecules (ligands, ions, waters, etc.)

### Movie Recording

- **Fixed duration** - When checked, calculates framerate to fit specified duration (1-300s)
- **Record all actions** - Records everything on screen until Stop is clicked (interactive mode)
- **Record** - Start recording
- **Stop** - Stop recording and encode movie


## File Naming

PDB files are sorted alphanumerically. Use zero-padding for proper ordering:
- `0001.pdb`, `0002.pdb`, ..., `0010.pdb`
- `frame_001.pdb`, `frame_002.pdb`, ...

## Optional Dependencies

### USalign

For pre-alignment of structures before loading, install [USalign](https://github.com/pylelab/USalign):

```bash
# With conda/mamba
conda install -c bioconda usalign

# Or download binary from https://zhanggroup.org/US-align/
```

The tool searches for USalign in:
- System PATH
- ~/miniforge3/bin/
- ~/miniconda3/bin/
- ~/anaconda3/bin/
- /usr/local/bin/
- /opt/homebrew/bin/

## Requirements

- ChimeraX 1.1 or later
- Python 3.7+
- USalign (optional, for pre-alignment)


