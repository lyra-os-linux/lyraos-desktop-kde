var launcherIcon = "lyra-launcher";
var vegaLauncher = "applications:org.lyraos.Vega.Qt.desktop";

var plasmaPanels = panels();
for (var panelIndex in plasmaPanels) {
    var widgets = plasmaPanels[panelIndex].widgets();
    for (var widgetIndex in widgets) {
        var widget = widgets[widgetIndex];

        if (widget.type === "org.kde.plasma.kickoff") {
            widget.currentConfigGroup = ["General"];
            widget.writeConfig("icon", launcherIcon);
        }

        if (widget.type === "org.kde.plasma.icontasks") {
            widget.currentConfigGroup = ["General"];
            var configured = widget.readConfig("launchers", []);
            var launchers = Array.isArray(configured)
                ? configured
                : String(configured).split(",").filter(function (entry) {
                    return entry;
                });

            launchers = launchers.filter(function (entry) {
                return entry.indexOf("org.kde.discover") === -1;
            });
            if (launchers.indexOf(vegaLauncher) === -1) {
                launchers.push(vegaLauncher);
            }

            widget.writeConfig("launchers", launchers);
        }
    }
}
