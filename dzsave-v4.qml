import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: window
    visible: true
    width: 1000
    height: 980
    minimumWidth: 780
    minimumHeight: 740
    title: "WSI DeepZoom Converter - QML"

    function indexOfValue(value) {
        for (var i = 0; i < controller.deepzoomFormats.length; i++) {
            if (controller.deepzoomFormats[i].value === value) {
                return i;
            }
        }
        return -1;
    }

    component ActionButton: Button {
        id: control
        property bool primary: false
        implicitHeight: 34
        leftPadding: 12
        rightPadding: 12
        font.weight: Font.DemiBold
        contentItem: Text {
            text: control.text
            font: control.font
            color: control.primary ? "white" : "#18324b"
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle {
            radius: 5
            color: !control.enabled ? "#e5e7eb"
                  : control.down ? (control.primary ? "#1e40af" : "#c8dcf2")
                  : control.hovered ? (control.primary ? "#1d4ed8" : "#dce9f7")
                  : control.primary ? "#2563eb" : "#edf3fa"
            border.color: control.activeFocus ? "#0f172a"
                         : control.primary ? "#1e40af" : "#7895b2"
            border.width: control.activeFocus ? 2 : 1
        }
    }

    component SectionToggle: ToolButton {
        id: control
        implicitHeight: 36
        leftPadding: 12
        rightPadding: 14
        hoverEnabled: true
        font.weight: Font.DemiBold
        font.pixelSize: 13
        contentItem: Text {
            text: (control.checked ? "▼  " : "▶  ") + control.text
            font: control.font
            color: "#18324b"
            horizontalAlignment: Text.AlignLeft
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: 6
            color: !control.enabled ? "#f3f4f6"
                  : control.down ? "#c6d9ed"
                  : control.checked ? "#e2ecf7"
                  : control.hovered ? "#f3f7fc" : "#edf3fa"
            border.color: control.activeFocus ? "#2563eb"
                         : control.checked ? "#587da3"
                         : control.hovered ? "#7895b2" : "#a9bbcd"
            border.width: control.activeFocus ? 2 : 1
        }
    }

    ScrollView {
        id: pageScroll
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: fixedBottom.top
        contentWidth: availableWidth
        clip: true

        ColumnLayout {
        width: pageScroll.availableWidth
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

            ColumnLayout {
                anchors.fill: parent

                RowLayout {
                    Label {
                        text: "Source WSI folder"
                        Layout.preferredWidth: 180
                    }
                    TextField {
                        text: controller.fields["input_dir"]
                        onTextEdited: controller.setField("input_dir", text)
                        Layout.fillWidth: true
                    }
                    ActionButton {
                        text: "Browse..."
                        onClicked: controller.browse("input_dir")
                    }
                }

                Repeater {
                    model: controller.destinations
                    delegate: RowLayout {
                        required property int index
                        required property string modelData
                        Layout.fillWidth: true

                        Label {
                            text: "Destination " + (index + 1)
                            Layout.preferredWidth: 180
                        }
                        TextField {
                            text: modelData
                            onEditingFinished: controller.setDestination(index, text)
                            Layout.fillWidth: true
                        }
                        ActionButton {
                            text: "Browse..."
                            onClicked: controller.browseDestination(index)
                        }
                        ActionButton {
                            text: "Remove"
                            enabled: index > 0 && controller.destinations.length > 1
                            onClicked: controller.removeDestination(index)
                        }
                    }
                }
                ActionButton {
                    text: "Add destination"
                    onClicked: controller.addDestination()
                    Layout.alignment: Qt.AlignRight
                }
            }
        }

        GroupBox {
            title: "Found WSI files (checked files will be converted)"
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
                    ActionButton {
                        text: "Select all"
                        enabled: !controller.isBusy
                        onClicked: controller.selectAllFiles(true)
                    }
                    ActionButton {
                        text: "Select none"
                        enabled: !controller.isBusy
                        onClicked: controller.selectAllFiles(false)
                    }
                }
            }
        }

        SectionToggle {
            id: optionsToggle
            text: checked
                  ? "Hide DeepZoom and Robocopy options"
                  : "Show DeepZoom and Robocopy options"
            checkable: true
            Layout.alignment: Qt.AlignLeft
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            visible: optionsToggle.checked

            ColumnLayout {
                Layout.fillWidth: true

                SectionToggle {
                    id: deepzoomOptionsToggle
                    text: checked ? "Hide DeepZoom and thumbnail" : "Show DeepZoom and thumbnail"
                    checkable: true
                    checked: true
                    Layout.alignment: Qt.AlignLeft
                }

                GroupBox {
                    visible: deepzoomOptionsToggle.checked
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
                        Label { text: "DeepZoom output format" }
                        ComboBox {
                            id: outputFormatSelector
                            objectName: "outputFormatSelector"
                            textRole: "label"
                            valueRole: "value"
                            model: controller.deepzoomFormats
                            currentIndex: indexOfValue(controller.fields["deepzoom_format"])
                            onActivated: controller.setField("deepzoom_format", currentValue)
                            Component.onCompleted: {
                                currentIndex = indexOfValue(controller.fields["deepzoom_format"])
                            }
                        }
                        Label { text: "WSI extensions (comma-separated)" }
                        TextField {
                            text: controller.fields["wsi_extensions"]
                            onTextEdited: controller.setField("wsi_extensions", text)
                            Layout.fillWidth: true
                        }
                        Label {
                            text: "Extensions must be supported by installed libvips loaders."
                            Layout.columnSpan: 2
                            wrapMode: Text.Wrap
                        }
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true

                SectionToggle {
                    id: robocopyOptionsToggle
                    text: checked ? "Hide Robocopy options" : "Show Robocopy options"
                    checkable: true
                    checked: true
                    Layout.alignment: Qt.AlignLeft
                }

                GroupBox {
                    visible: robocopyOptionsToggle.checked
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
        }

        SectionToggle {
            id: activityToggle
            text: checked ? "Hide Activity" : "Show Activity"
            checkable: true
            checked: true
            Layout.alignment: Qt.AlignLeft
        }

        GroupBox {
            visible: activityToggle.checked
            Layout.fillWidth: true

            ColumnLayout {
                width: parent.width
                Label {
                    text: controller.statusText
                    Layout.fillWidth: true
                }
                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: controller.reportInfo
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }
                    ActionButton {
                        text: "Open report"
                        enabled: controller.reportPath.length > 0
                        onClicked: controller.openReport()
                    }
                }
                SectionToggle {
                    id: liveDetailsToggle
                    text: checked ? "Hide live conversion details" : "Show live conversion details"
                    checkable: true
                    Layout.alignment: Qt.AlignLeft
                }

                ColumnLayout {
                    visible: liveDetailsToggle.checked
                    Layout.fillWidth: true

                    GridLayout {
                        columns: 4
                        Layout.fillWidth: true
                        columnSpacing: 10
                        rowSpacing: 4
                        Label { text: "Current file" }
                        Label {
                            text: controller.activityDetails.file
                            elide: Text.ElideMiddle
                            Layout.fillWidth: true
                        }
                        Label { text: "Resolution" }
                        Label { text: controller.activityDetails.resolution }
                        Label { text: "Source load" }
                        Label { text: controller.activityDetails.load }
                        Label { text: "DeepZoom" }
                        Label { text: controller.activityDetails.deepzoom }
                        Label { text: "Thumbnail" }
                        Label { text: controller.activityDetails.thumbnail }
                        Label { text: "Copy" }
                        Label {
                            text: controller.activityDetails.copy
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }
                        Label { text: "Slide total" }
                        Label { text: controller.activityDetails.slide }
                        Label { text: "Run elapsed" }
                        Label { text: controller.activityDetails.elapsed }
                        Label { text: "File totals" }
                        Label {
                            text: controller.activityDetails.counts
                            Layout.columnSpan: 3
                        }
                        Label { text: "Output paths" }
                        Label {
                            text: controller.activityDetails.outputs
                            wrapMode: Text.Wrap
                            Layout.columnSpan: 3
                            Layout.fillWidth: true
                        }
                    }
                    Label {
                        text: controller.runSummary
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }
                }

                SectionToggle {
                    id: resultsToggle
                    text: checked ? "Hide per-file results" : "Show per-file results"
                    checkable: true
                    Layout.alignment: Qt.AlignLeft
                }

                ScrollView {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 130
                    contentWidth: 1400
                    visible: resultsToggle.checked
                    ScrollBar.horizontal.policy: ScrollBar.AsNeeded
                    ColumnLayout {
                        width: 1400
                        RowLayout {
                            Layout.fillWidth: true
                            Label { text: "File"; Layout.preferredWidth: 200 }
                            Label { text: "Resolution"; Layout.preferredWidth: 110 }
                            Label { text: "Load"; Layout.preferredWidth: 60 }
                            Label { text: "DeepZoom"; Layout.preferredWidth: 120 }
                            Label { text: "Thumbnail"; Layout.preferredWidth: 120 }
                            Label { text: "Copy"; Layout.preferredWidth: 60 }
                            Label { text: "Total"; Layout.preferredWidth: 60 }
                            Label { text: "Status"; Layout.preferredWidth: 65 }
                            Label { text: "Copy destinations"; Layout.preferredWidth: 180 }
                            Label { text: "Output paths"; Layout.preferredWidth: 220 }
                            Label { text: "Error"; Layout.preferredWidth: 150 }
                        }
                        ListView {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 105
                            clip: true
                            model: controller.resultRows
                            delegate: RowLayout {
                                required property var modelData
                                width: ListView.view.width
                                Label {
                                    text: modelData.file
                                    elide: Text.ElideMiddle
                                    Layout.preferredWidth: 200
                                }
                                Label { text: modelData.resolution; Layout.preferredWidth: 110 }
                                Label { text: modelData.load; Layout.preferredWidth: 60 }
                                Label { text: modelData.deepzoom; Layout.preferredWidth: 120 }
                                Label { text: modelData.thumbnail; Layout.preferredWidth: 120 }
                                Label { text: modelData.copy; Layout.preferredWidth: 60 }
                                Label { text: modelData.total; Layout.preferredWidth: 60 }
                                Label {
                                    text: modelData.status
                                    Layout.preferredWidth: 65
                                }
                                Label {
                                    text: modelData.copy_destinations
                                    elide: Text.ElideRight
                                    Layout.preferredWidth: 180
                                }
                                Label {
                                    text: modelData.outputs
                                    elide: Text.ElideRight
                                    Layout.preferredWidth: 220
                                }
                                Label {
                                    text: modelData.error
                                    elide: Text.ElideRight
                                    Layout.preferredWidth: 150
                                }
                            }
                        }
                    }
                }
                SectionToggle {
                    id: textOutputToggle
                    text: checked ? "Hide detailed text output" : "Show detailed text output"
                    checkable: true
                }
                ScrollView {
                    Layout.fillWidth: true
                    visible: textOutputToggle.checked
                    Layout.minimumHeight: textOutputToggle.checked ? 180 : 0
                    Layout.preferredHeight: textOutputToggle.checked ? 180 : 0
                    clip: true
                    TextArea {
                        text: controller.logText
                        readOnly: true
                        wrapMode: TextEdit.Wrap
                        font.family: "Consolas"
                        width: parent.width
                        height: Math.max(180, implicitHeight)
                    }
                }
            }
        }

        }
    }

    ColumnLayout {
        id: fixedBottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        spacing: 6

        GroupBox {
            title: "Conversion progress"
            Layout.fillWidth: true
            ColumnLayout {
                width: parent.width
                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: "Overall — " + controller.progressDescription
                        Layout.fillWidth: true
                    }
                    Label { text: controller.progressPercent + "%" }
                }
                ProgressBar {
                    from: 0
                    to: Math.max(1, controller.progressMaximum)
                    value: controller.progressValue
                    Layout.fillWidth: true
                }
                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: "Current slide — " + controller.progressDescription
                        Layout.fillWidth: true
                    }
                    Label { text: controller.stagePercent + "%" }
                }
                ProgressBar {
                    from: 0
                    to: 4
                    value: controller.stageProgress
                    Layout.fillWidth: true
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            ActionButton {
                text: "Scan files"
                enabled: !controller.isBusy
                onClicked: controller.scan()
            }
            ActionButton {
                text: "Start conversion"
                primary: true
                enabled: !controller.isBusy
                onClicked: controller.startConversion()
            }
        }
    }
}
