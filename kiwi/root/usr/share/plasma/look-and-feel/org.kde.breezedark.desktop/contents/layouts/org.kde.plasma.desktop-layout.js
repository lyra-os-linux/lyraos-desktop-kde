loadTemplate("org.kde.plasma.desktop.defaultPanel")

// Plasma can recreate a panel on screen -1 when a global theme reapplies its
// desktop layout. Keep the upstream template, but attach its result to the
// enabled output detected by the Lyra first-login initializer.
var panelList = panels();
for (var panelIndex = 0; panelIndex < panelList.length; panelIndex++) {
    if (panelList[panelIndex].screen < 0) {
        panelList[panelIndex].screen = 0;
    }
}

// Breeze uses Image=Next, which discards the branded wallpaper when users
// apply the desktop layout while switching global themes.
var desktopList = desktops();
for (var desktopIndex = 0; desktopIndex < desktopList.length; desktopIndex++) {
    var desktop = desktopList[desktopIndex];
    desktop.wallpaperPlugin = "org.kde.image";
    desktop.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    desktop.writeConfig("Image", "file:///usr/share/backgrounds/lyra/2702-dawn.png");
}
