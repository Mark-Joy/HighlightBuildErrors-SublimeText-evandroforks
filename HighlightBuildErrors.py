import sublime, sublime_plugin
import importlib
import re
import os

SETTINGS_FILE = "HighlightBuildErrors.sublime-settings"
REGION_KEY_PREFIX = "build_errors_color"
REGION_FLAGS = {
    "none": sublime.HIDDEN,
    "fill": 0,
    "outline": sublime.DRAW_NO_FILL,
    "solid_underline": sublime.DRAW_NO_FILL|sublime.DRAW_NO_OUTLINE|sublime.DRAW_SOLID_UNDERLINE,
    "stippled_underline":  sublime.DRAW_NO_FILL|sublime.DRAW_NO_OUTLINE|sublime.DRAW_STIPPLED_UNDERLINE,
    "squiggly_underline":  sublime.DRAW_NO_FILL|sublime.DRAW_NO_OUTLINE|sublime.DRAW_SQUIGGLY_UNDERLINE
}

try:
    defaultExec = importlib.import_module("Better Build System").BetterBuidSystem
except:
    defaultExec = importlib.import_module("Default.exec")

try:
    ansiEscape = importlib.import_module("ANSIescape").ansi
except:
    pass

g_errors = {}
g_show_errors = True
g_color_configs = []

def plugin_loaded():
    global g_settings
    g_settings = sublime.load_settings(SETTINGS_FILE)
    g_settings.add_on_change("colors", load_config)
    load_config()

def load_config():
    global g_settings
    global g_color_configs, g_default_color
    g_settings = sublime.load_settings(SETTINGS_FILE)
    g_color_configs = g_settings.get("colors", [{"color": "sublimelinter.mark.error"}])
    for config in g_color_configs:
        if "regex" in config:
            config["compiled_regex"] = re.compile(config["regex"])

def normalize_path(file_name):
    return os.path.normcase(os.path.abspath(file_name))

def update_errors_in_view(view):
    global g_color_configs, g_default_color
    file_name = view.file_name()
    if file_name is None:
        return
    file_name = normalize_path(file_name)
    for idx, config in enumerate(g_color_configs):
        region_key = REGION_KEY_PREFIX + str(idx)
        scope = config["scope"] if "scope" in config else "invalid"
        icon = config["icon"] if "icon" in config else ""
        default_display = "fill" if "scope" in config else "none"
        display = config["display"] if "display" in config else default_display
        if g_show_errors:
            regions = [e.get_region(view) for e in g_errors if e.file_name == file_name and e.color_index == idx]
            view.add_regions(region_key, regions, scope, icon, REGION_FLAGS[display])
        else:
            view.erase_regions(region_key)

def update_all_views(window):
    for view in window.views():
        update_errors_in_view(view)

def remove_errors_in_view(view):
    global g_color_configs
    for idx, val in enumerate(g_color_configs):
        view.erase_regions(REGION_KEY_PREFIX + str(idx))
    g_errors.clear()

class ViewEventListener(sublime_plugin.EventListener):
    def on_load_async(self, view):
        update_errors_in_view(view)

    def on_activated_async(self, view):
        update_errors_in_view(view)

    def on_window_command(self, window, command, args):
        if command == "build":
            for view in window.views():
                remove_errors_in_view(view)


def get_filename(matchObject):
    # only keep last line (i've seen a bad regex that capture several lines)
    return normalize_path(matchObject.group(1).splitlines()[-1])

def get_line(matchObject):
    if len(matchObject.groups()) < 3:
        return None
    try:
        return int(matchObject.group(2))
    except ValueError:
        return None

def get_column(matchObject):
    # column is optional, the last one is always the message
    if len(matchObject.groups()) < 4 or matchObject.group(3) is None:
        return None
    try:
        return int(matchObject.group(3))
    except ValueError:
        return None

def get_message(matchObject):
    if len(matchObject.groups()) < 3:
        return None
    # column is optional, the last one is always the message
    return matchObject.group(len(matchObject.groups()))

class ErrorLine:
    def __init__(self, matchObject):
        global g_color_configs
        # only keep last line (i've seen a bad regex that capture several lines)
        self.file_name = get_filename(matchObject);
        self.line = get_line(matchObject);
        self.column = get_column(matchObject)
        self.message = get_message(matchObject)
        if self.message == None: return
        self.color_index = 0
        for config in g_color_configs:
            if not "compiled_regex" in config:
                break
            if config["compiled_regex"].search(self.message):
                break
            self.color_index = self.color_index+1;

    def get_region(self, view):
        if self.line is None:
            return None
        if self.column is None:
            point = view.text_point(self.line-1, 0)
            return view.full_line(point)
        point = view.text_point(self.line-1, self.column-1)
        point_class = view.classify(point)
        if point_class & (sublime.CLASS_WORD_START|sublime.CLASS_WORD_END):
            return view.word(point)
        else:
            return view.full_line(point)

class ErrorParser:
    def __init__(self, pattern):
        self.regex = re.compile(pattern, re.MULTILINE)
        self.bad_regex = self.regex.groups < 3 or self.regex.groups > 4
        if self.bad_regex:
            print("Highlight Build Errors plugin warning: invalid configuration\nThe regular expression must capture filename,line,[column,]message\nPlease fix the 'file_regex' in build system configuration.")

    def parse(self, text):
        if self.bad_regex:
            return []
        else:
            return [ErrorLine(m) for m in self.regex.finditer(text)]


def fixHorizontalScrollGlitch(self):
    """
        The output build panel is completely scrolled horizontally to the right when there are build errors
        https://github.com/SublimeTextIssues/Core/issues/2239
    """
    view = self.output_view
    new_x = 0

    viewport_height = view.viewport_extent()[1]
    current_y_position = view.viewport_position()[1]

    # print("viewport_height: %s, current_y_position: %s" % (viewport_height, current_y_position))
    # if current_y_position > viewport_height:
    view.set_viewport_position((new_x, current_y_position), False)


def forceShowBuildPanel(self, proc):

    if not self.is_word_wrap_enabled:
        fixHorizontalScrollGlitch(self)

    if g_settings.get("force_show_build_panel", False):
        exit_code = proc.exit_code()
        output_view = self.output_view
        errors_len = len(output_view.find_all_results())

        # How to track if an output panel is closed/hidden?
        # https://forum.sublimetext.com/t/how-to-track-if-an-output-panel-is-closed-hidden/8453
        if ( exit_code \
                or errors_len ) \
                and not output_view.window():

            output_view.show(0)
            self.window.run_command("show_panel", {"panel": "output.exec"})


def setWordWrapSetting(self):

    if not hasattr(self, "output_view"):
        return

    output = self.output_view.substr(sublime.Region(0, self.output_view.size()))

    project_settings = self.window.project_data().get("settings", {})
    is_word_wrap_enabled = project_settings.get("is_output_build_word_wrap_enabled", True)
    self.is_word_wrap_enabled = is_word_wrap_enabled

    if not is_word_wrap_enabled:
        output_view_settings = self.output_view.settings()
        output_view_settings.set("word_wrap", False)
        # highlight_line doesn't work unless gutter is true
        # https://github.com/SublimeTextIssues/Core/issues/586
        # output_view_settings.set("highlight_line", True)


def doHighlighting(self):
    output = self.output_view.substr(sublime.Region(0, self.output_view.size()))

    # First try to get the setting `result_file_regex` on the current window project settings
    project_settings = self.window.project_data().get("settings", {})
    error_pattern = project_settings.get("result_file_regex", None)

    if not error_pattern:
        output_view_settings = self.output_view.settings()
        error_pattern = output_view_settings.get("result_file_regex")

    error_parser = ErrorParser(error_pattern)

    global g_errors
    g_errors = error_parser.parse(output)
    update_all_views(self.window)


class ExecCommand(defaultExec.ExecCommand):

    def run(self, *args, **kwargs):
        super(ExecCommand, self).run(*args, **kwargs)
        setWordWrapSetting(self)

    def on_finished(self, proc):
        """It is the entry point after the process is finished."""
        super(ExecCommand, self).on_finished(proc)
        doHighlighting(self)
        forceShowBuildPanel(self, proc)


try:
    class AnsiColorBuildCommand(ansiEscape.AnsiColorBuildCommand):

        def run(self, *args, **kwargs):
            super(AnsiColorBuildCommand, self).run(*args, **kwargs)
            setWordWrapSetting(self)

        def finish(self, proc):
            super(AnsiColorBuildCommand, self).finish(proc)
            doHighlighting(self)
            forceShowBuildPanel(self, proc)

except:
    pass


class HideBuildErrorsCommand(sublime_plugin.WindowCommand):

    def is_enabled(self):
        return g_show_errors

    def run(self):
        global g_show_errors
        g_show_errors = False
        update_all_views(self.window)



class ShowBuildErrorsCommand(sublime_plugin.WindowCommand):

    def is_enabled(self):
        return not g_show_errors

    def run(self):
        global g_show_errors
        g_show_errors = True
        update_all_views(self.window)
