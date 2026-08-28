import QtQuick 2.15

// Keep the Lyra identity as a small, maintainable layer over Plasma's
// distribution-tested Breeze greeter. The loaded component retains Breeze's
// keyboard, pointer, accessibility, session and multi-screen behavior while
// reading this theme's wallpaper, logo and color configuration.
Loader {
    anchors.fill: parent
    source: "../breeze/Main.qml"
}
