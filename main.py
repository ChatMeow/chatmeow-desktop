import sys
import time
from io import BytesIO
import qrcode
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QMessageBox,
    QTextEdit,
    QInputDialog,
    QLineEdit,
)
from PyQt5.QtGui import QPixmap, QIcon, QImage
from PyQt5.QtCore import pyqtSlot, QThread, pyqtSignal, Qt
import serial
import serial.tools.list_ports


class CommandThread(QThread):
    output = pyqtSignal(str)
    completed = pyqtSignal()

    def __init__(self, serial_port, command):
        super().__init__()
        self.serial_port = serial_port
        self.command = command

    def run(self):
        if self.serial_port and self.serial_port.isOpen():
            self.serial_port.write((self.command + "\n").encode())
            output = ""
            while True:
                line = self.serial_port.read_until().decode()
                if line.startswith("root@orangepizero:"):
                    break
                if not line.startswith(self.command):
                    output += line
            self.output.emit(output)
        self.completed.emit()


class SerialApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.title = "ChatMeow配网工具(测试)"
        self.left = 50
        self.top = 50
        self.width = 400
        self.height = 450
        self.serial_port = None
        self.command_thread = None
        self.initUI()

    def initUI(self):
        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)

        widget = QWidget(self)
        self.setCentralWidget(widget)
        layout = QVBoxLayout()

        self.comboBox = QComboBox(self)
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.comboBox.addItem(port.device)
        layout.addWidget(QLabel("选择串口:"))
        layout.addWidget(self.comboBox)

        self.openButton = QPushButton("打开串口连接", self)
        self.openButton.clicked.connect(self.toggle_serial_connection)
        layout.addWidget(self.openButton)

        self.wifiComboBox = QComboBox(self)
        layout.addWidget(QLabel("可用WiFi网络:"))
        layout.addWidget(self.wifiComboBox)

        self.scanButton = QPushButton("扫描WiFi网络", self)
        self.scanButton.clicked.connect(
            lambda: self.send_command(
                "nmcli -t -f ssid dev wifi | grep --color=never -v '^--' | sort | uniq"
            )
        )
        layout.addWidget(self.scanButton)

        self.connectButton = QPushButton("连接到WiFi", self)
        self.connectButton.clicked.connect(self.connect_wifi)
        layout.addWidget(self.connectButton)

        self.cancelButton = QPushButton("取消当前操作", self)
        self.cancelButton.clicked.connect(self.cancel_command)
        layout.addWidget(self.cancelButton)

        self.connectionStatusLabel = QLabel("未连接到WiFi")
        layout.addWidget(self.connectionStatusLabel)

        self.ipAddressLabel = QLabel("IP地址: 未知")
        layout.addWidget(self.ipAddressLabel)

        self.qrCodeLabel = QLabel(self)
        layout.addWidget(self.qrCodeLabel)

        self.terminal = QTextEdit(self)
        self.terminal.setReadOnly(True)
        layout.addWidget(self.terminal)

        widget.setLayout(layout)

    def toggle_serial_connection(self):
        if self.serial_port and self.serial_port.isOpen():
            self.close_serial_connection()
        else:
            self.open_serial_connection()

    def open_serial_connection(self):
        selected_port = self.comboBox.currentText()
        try:
            self.serial_port = serial.Serial(selected_port, 115200, timeout=1)
            self.terminal.append(f"串口已连接: {selected_port}")
            self.openButton.setText("关闭串口连接")
            self.serial_port.write(b"\r\n")
            time.sleep(0.5)
            self.serial_port.reset_input_buffer()
            self.serial_port.read_until()
            self.scan_wifi()
        except Exception as e:
            QMessageBox.warning(self, "警告", f"无法打开串口：{str(e)}")

    def close_serial_connection(self):
        if self.serial_port:
            self.serial_port.close()
            self.terminal.append("串口已断开")
            self.openButton.setText("打开串口连接")
            self.openButton.setEnabled(True)

    def send_command(self, command):
        if not self.serial_port or not self.serial_port.isOpen():
            QMessageBox.warning(self, "警告", "串口未连接！")
            return
        self.command_thread = CommandThread(self.serial_port, command)
        self.command_thread.output.connect(self.handle_output)
        self.command_thread.completed.connect(self.command_finished)
        self.scanButton.setEnabled(False)
        self.connectButton.setEnabled(False)
        self.command_thread.start()

    def handle_output(self, output):
        self.terminal.append(output)
        if "nmcli -t -f ssid dev wifi" in self.command_thread.command:
            self.wifiComboBox.clear()
            for ssid in output.strip().split("\n"):
                if ssid:
                    self.wifiComboBox.addItem(ssid)

    def command_finished(self):
        self.terminal.append("命令执行完成")
        self.update_wifi_status()
        self.scanButton.setEnabled(True)
        self.connectButton.setEnabled(True)

    def cancel_command(self):
        if self.serial_port and self.serial_port.isOpen():
            self.serial_port.write(b"\x03")
            self.terminal.append("发送取消命令...")
            time.sleep(0.5)
            self.serial_port.reset_input_buffer()
            self.terminal.append("取消命令发送完成")

    def scan_wifi(self):
        self.send_command(
            "nmcli -t -f ssid dev wifi | grep --color=never -v '^--' | sort | uniq"
        )

    def connect_wifi(self):
        network_name = self.wifiComboBox.currentText().strip()
        if network_name:
            password, ok = QInputDialog.getText(
                self, "输入密码", f"输入WiFi密码: {network_name}", QLineEdit.Password
            )
            if ok:
                print(network_name)
                print(password)
                self.send_command(
                    f"nmcli dev wifi connect '{network_name}' password '{password}'"
                )
                print(f"nmcli dev wifi connect '{network_name}' password '{password}'")

    def update_wifi_status(self):
        if self.serial_port and self.serial_port.isOpen():
            self.command_thread = CommandThread(
                self.serial_port,
                "nmcli -t -f GENERAL.CONNECTION,IP4.ADDRESS device show | grep 'GENERAL.CONNECTION\|IP4.ADDRESS' --color=never",
            )
            self.command_thread.output.connect(self.handle_wifi_status)
            self.command_thread.completed.connect(
                lambda: self.terminal.append("WiFi状态与IP地址更新完成")
            )
            self.command_thread.start()
        else:
            QMessageBox.warning(self, "警告", "串口未连接！")

    def handle_wifi_status(self, output):
        lines = output.strip().split("\n")
        ssid = ip_address = "未知"
        wired_ip = None
        print(lines)
        for line in lines:
            if "GENERAL.CONNECTION:" in line:
                connection_name = line.split(":")[1].strip().replace("\r", "")
                if connection_name:  # 检查连接名是否非空
                    ssid = connection_name  # 更新SSID为当前连接名称
            elif "IP4.ADDRESS" in line:
                current_ip = line.split(":", 1)[1].strip().split("/", 1)[0]
                if "127.0.0.1" not in current_ip:
                    if "Wired connection" in ssid and not wired_ip:
                        wired_ip = current_ip  # 仅当为有线连接且尚未记录IP时保存IP地址
                    if not ssid.startswith("Wired connection"):
                        ip_address = current_ip  # 如果不是有线连接，则更新IP地址为最新的无线连接IP

        # 使用有线IP地址（如果存在）
        if wired_ip:
            ip_address = wired_ip
            self.connectionStatusLabel.setText(f"已连接到有线网络")
        elif ssid != "未知":
            self.connectionStatusLabel.setText(f"已连接到WiFi: {ssid}")
        else:
            self.connectionStatusLabel.setText("未连接到任何网络")

        self.ipAddressLabel.setText(f"IP地址: {ip_address}")
        self.update_qr_code(ip_address)  # 更新二维码

    def update_qr_code(self, ip_address):
        if ip_address != "未知":
            url = f"http://{ip_address}"
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            byte_array = BytesIO()
            img.save(byte_array, format="PNG")
            byte_array.seek(0)
            pixmap = QPixmap()
            pixmap.loadFromData(byte_array.getvalue())
            self.qrCodeLabel.setPixmap(pixmap)
            self.qrCodeLabel.setAlignment(Qt.AlignCenter)
        else:
            self.qrCodeLabel.clear()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    ex = SerialApp()
    ex.show()
    sys.exit(app.exec_())
