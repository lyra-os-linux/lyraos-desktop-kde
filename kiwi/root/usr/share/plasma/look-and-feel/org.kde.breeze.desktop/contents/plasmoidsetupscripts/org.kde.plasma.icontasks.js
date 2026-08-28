applet.currentConfigGroup = ["General"];

var configured = applet.readConfig("launchers", []);
var launchers = Array.isArray(configured)
    ? configured
    : String(configured).split(",").filter(function (entry) {
        return entry;
    });

launchers = launchers.filter(function (entry) {
    return entry.indexOf("org.kde.discover") === -1;
});

var vegaLauncher = "applications:org.lyraos.Vega.Qt.desktop";
if (launchers.indexOf(vegaLauncher) === -1) {
    launchers.push(vegaLauncher);
}

applet.writeConfig("launchers", launchers);
applet.reloadConfig();
