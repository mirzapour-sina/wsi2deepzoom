import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: window
    visible: true
    width: 1000
    height: 900
    minimumWidth: 780
    minimumHeight: 680
    title: "WSI DeepZoom Converter - QML"

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 10

        Label {
            text: "WSI DeepZoom Converter"
            font.pixelSize: 22
            font.bold: true
        }

        Label {
            text: "Convert TIFF slides, generate thumbnails, and copy DeepZoom output."
            Layout.fillWidth: true
        }

        GroupBox {
            title: "Folders"
            Layout.fillWidth: true

            GridLayout {
                anchors.fill: parent
                columns: 3
                columnSpacing: 8
                rowSpacing: 6

                Repeater {
                    model: [
                        { key: "input_dir", label: "Source WSI folder" },
                        { key: "primary_dir", label: "Primary destination" },
                        { key: "secondary_dir", label: "Secondary destination" }
                    ]

                    delegate: RowLayout {
                        required property var modelData
                        Layout.columnSpan: 3
                        Layout.fillWidth: true

                        Label {
                            text: modelData.label
                            Layout.preferredWidth: 180
                        }

                        TextField {
                            text: controller.fields[modelData.key]
                            onTextEdited: controller.setField(modelData.key, text)
                            Layout.fillWidth: true
                        }

                        Button {
                            text: "Browse..."
                            onClicked: controller.browse(modelData.key)
                        }
                    }
                }
            }
        }

        GroupBox {
            title: "Found TIFF files (checked files will be converted)"
            Layout.fillWidth: true
            Layout.preferredHeight: 190

            ColumnLayout {
                anchors.fill: parent
                Label {
                    text: controller.selectionSummary
                }
                ListView {
                    id: fileView
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: controller.scannedFiles
                    delegate: CheckBox {
                        required property int index
                        required property var modelData
                        width: fileView.width
                        text: modelData.path
                        checked: modelData.checked
                        enabled: !controller.isBusy
                        onToggled: controller.setFileSelected(index, checked)
                    }
                }
                RowLayout {
                    Button {
                        text: "Select all"
                        enabled: !controller.isBusy
                        onClicked: controller.selectAllFiles(true)
                    }
                    Button {
                        text: "Select none"
                        enabled: !controller.isBusy
                        onClicked: controller.selectAllFiles(false)
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            GroupBox {
                title: "Conversion and thumbnail settings"
                Layout.fillWidth: true

                GridLayout {
                    anchors.fill: parent
                    columns: 2
                    columnSpacing: 8
                    rowSpacing: 5

                    Label { text: "DeepZoom JPEG quality" }
                    TextField {
                        text: controller.fields["jpeg_quality"]
                        onTextEdited: controller.setField("jpeg_quality", text)
                    }
                    Label { text: "Thumbnail max size (pixels)" }
                    TextField {
                        text: controller.fields["thumbnail_size"]
                        onTextEdited: controller.setField("thumbnail_size", text)
                    }
                    Label { text: "Thumbnail JPEG quality" }
                    TextField {
                        text: controller.fields["thumbnail_quality"]
                        onTextEdited: controller.setField("thumbnail_quality", text)
                    }
                }
            }

            GroupBox {
                title: "Robocopy settings"
                Layout.fillWidth: true

                GridLayout {
                    anchors.fill: parent
                    columns: 2
                    columnSpacing: 8
                    rowSpacing: 5

                    Label { text: "Threads" }
                    TextField {
                        text: controller.fields["robocopy_threads"]
                        onTextEdited: controller.setField("robocopy_threads", text)
                    }
                    Label { text: "Retry count" }
                    TextField {
                        text: controller.fields["robocopy_retries"]
                        onTextEdited: controller.setField("robocopy_retries", text)
                    }
                    Label { text: "Retry wait (seconds)" }
                    TextField {
                        text: controller.fields["robocopy_wait"]
                        onTextEdited: controller.setField("robocopy_wait", text)
                    }
                }
            }
        }

        GroupBox {
            title: "Activity"
            Layout.fillWidth: true
            Layout.fillHeight: true

            ColumnLayout {
                anchors.fill: parent
                Label {
                    text: controller.statusText
                    Layout.fillWidth: true
                }
                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    TextArea {
                        text: controller.logText
                        readOnly: true
                        wrapMode: TextEdit.Wrap
                        font.family: "Consolas"
                    }
                }
            }
        }

        ProgressBar {
            from: 0
            to: Math.max(1, controller.progressMaximum)
            value: controller.progressValue
            Layout.fillWidth: true
        }

        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            Button {
                text: "Scan files"
                enabled: !controller.isBusy
                onClicked: controller.scan()
            }
            Button {
                text: "Start conversion"
                enabled: !controller.isBusy
                onClicked: controller.startConversion()
            }
        }
    }
}
