# vim: set expandtab shiftwidth=4 softtabstop=4:

from chimerax.core.commands import CmdDesc, register, StringArg, IntArg, BoolArg


def register_ames_command(logger):
    """Register the ames command and subcommands."""
    
    # ames align - sequential alignment
    desc = CmdDesc(
        optional=[("chain", StringArg)],
        synopsis="Sequentially align all loaded structures using matchmaker"
    )
    register("ames align", desc, ames_align, logger=logger)
    
    # ames show - show specific frame
    desc = CmdDesc(
        required=[("frame", IntArg)],
        synopsis="Show specific frame (1-indexed)"
    )
    register("ames show", desc, ames_show, logger=logger)
    
    # ames play - start playback
    desc = CmdDesc(
        optional=[("speed", IntArg)],
        synopsis="Start trajectory playback"
    )
    register("ames play", desc, ames_play, logger=logger)
    
    # ames stop - stop playback
    desc = CmdDesc(
        synopsis="Stop trajectory playback"
    )
    register("ames stop", desc, ames_stop, logger=logger)


def _get_tool(session):
    """Get or create the AMES viewer tool."""
    from chimerax.core.tools import get_singleton
    from .tool import AMESViewerTool
    return get_singleton(session, AMESViewerTool, "AMES Viewer", create=True)


def ames_align(session, chain="A"):
    """Sequentially align all loaded structures."""
    from chimerax.atomic import AtomicStructure
    from chimerax.core.commands import run
    
    # Get all atomic structures, sorted by ID
    models = sorted(
        [m for m in session.models.list() if isinstance(m, AtomicStructure)],
        key=lambda m: m.id
    )
    
    if len(models) < 2:
        session.logger.warning("Need at least 2 structures for alignment")
        return
    
    session.logger.info(f"Aligning {len(models)} structures sequentially (chain {chain})...")
    
    for i in range(1, len(models)):
        prev_spec = f"#{models[i-1].id_string}/{chain}"
        curr_spec = f"#{models[i].id_string}/{chain}"
        
        try:
            run(session, f"matchmaker {curr_spec} to {prev_spec}")
            session.logger.info(f"Aligned {curr_spec} to {prev_spec}")
        except Exception as e:
            session.logger.warning(f"Failed: {curr_spec} to {prev_spec}: {e}")
    
    session.logger.info("Sequential alignment complete")


def ames_show(session, frame):
    """Show specific frame (1-indexed)."""
    tool = _get_tool(session)
    
    if not tool.structures:
        session.logger.warning("No trajectory loaded")
        return
    
    # Convert to 0-indexed
    tool._show_frame(frame - 1)


def ames_play(session, speed=None):
    """Start trajectory playback."""
    tool = _get_tool(session)
    
    if speed is not None:
        tool.play_speed = speed
        tool.speed_spin.setValue(speed)
    
    tool._start_playback()


def ames_stop(session):
    """Stop trajectory playback."""
    tool = _get_tool(session)
    tool._stop_playback()
