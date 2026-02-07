# vim: set expandtab shiftwidth=4 softtabstop=4:

from chimerax.core.toolshed import BundleAPI


class _AMESViewerAPI(BundleAPI):

    api_version = 1

    @staticmethod
    def start_tool(session, bi, ti):
        """Called when tool is requested to start."""
        if ti.name == "AMES Viewer":
            from .tool import AMESViewerTool
            return AMESViewerTool(session, ti.name)
        return None

    @staticmethod
    def register_command(bi, ci, logger):
        """Register the 'ames' command."""
        from . import cmd
        cmd.register_ames_command(logger)


bundle_api = _AMESViewerAPI()
