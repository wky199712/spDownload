import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Window 2.15

ApplicationWindow {
    id: window
    visible: true
    width: 1280
    height: 720
    title: "视频播放器"
    
    property alias mpvContainer: mpvContainer
    
    Rectangle {
        id: mpvContainer
        anchors.fill: parent
        color: "#000000"  // 修复：确保颜色值用引号包围
        
        Text {
            anchors.centerIn: parent
            text: "视频播放区域"
            color: "#ffffff"  // 修复：确保颜色值用引号包围
            font.pixelSize: 24
            visible: !mpvObj.playing
        }
        
        // 控制栏
        Rectangle {
            id: controlBar
            anchors.bottom: parent.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            height: 60
            color: "#80000000"  // 修复：半透明黑色，确保用引号
            
            Row {
                anchors.centerIn: parent
                spacing: 20
                
                Button {
                    text: mpvObj.paused ? "播放" : "暂停"
                    onClicked: mpvObj.togglePause()
                    
                    background: Rectangle {
                        color: "#00a1d6"  // 修复：确保颜色值用引号
                        radius: 4
                    }
                    
                    contentItem: Text {
                        text: parent.text
                        color: "#ffffff"  // 修复：确保颜色值用引号
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
                
                Slider {
                    id: progressSlider
                    width: 300
                    from: 0
                    to: mpvObj.duration
                    value: mpvObj.position
                    
                    onMoved: mpvObj.seek(value)
                    
                    background: Rectangle {
                        x: progressSlider.leftPadding
                        y: progressSlider.topPadding + progressSlider.availableHeight / 2 - height / 2
                        implicitWidth: 200
                        implicitHeight: 4
                        width: progressSlider.availableWidth
                        height: implicitHeight
                        radius: 2
                        color: "#404040"  // 修复：确保颜色值用引号
                        
                        Rectangle {
                            width: progressSlider.visualPosition * parent.width
                            height: parent.height
                            color: "#00a1d6"  // 修复：确保颜色值用引号
                            radius: 2
                        }
                    }
                    
                    handle: Rectangle {
                        x: progressSlider.leftPadding + progressSlider.visualPosition * (progressSlider.availableWidth - width)
                        y: progressSlider.topPadding + progressSlider.availableHeight / 2 - height / 2
                        implicitWidth: 16
                        implicitHeight: 16
                        radius: 8
                        color: progressSlider.pressed ? "#ffffff" : "#00a1d6"  // 修复：确保颜色值用引号
                        border.color: "#ffffff"  // 修复：确保颜色值用引号
                        border.width: 1
                    }
                }
                
                Text {
                    text: formatTime(mpvObj.position) + " / " + formatTime(mpvObj.duration)
                    color: "#ffffff"  // 修复：确保颜色值用引号
                    verticalAlignment: Text.AlignVCenter
                }
                
                Button {
                    text: "关闭"
                    onClicked: window.close()
                    
                    background: Rectangle {
                        color: "#ff4444"  // 修复：确保颜色值用引号
                        radius: 4
                    }
                    
                    contentItem: Text {
                        text: parent.text
                        color: "#ffffff"  // 修复：确保颜色值用引号
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }
        }
    }
    
    function formatTime(seconds) {
        if (isNaN(seconds) || seconds < 0) return "00:00"
        var minutes = Math.floor(seconds / 60)
        var secs = Math.floor(seconds % 60)
        return (minutes < 10 ? "0" : "") + minutes + ":" + (secs < 10 ? "0" : "") + secs
    }
}