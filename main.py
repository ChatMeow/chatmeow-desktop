import base64
import sys
import time
from io import BytesIO
import qrcode  # Import the qrcode library
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QComboBox, \
    QMessageBox, QTextEdit, QInputDialog, QLineEdit, QLabel, QSystemTrayIcon
from PyQt5.QtGui import QPixmap, QIcon, QImage
from PyQt5.QtCore import QThread, pyqtSignal
import serial
import serial.tools.list_ports
from icon import icon_data_base64  # Import the icon data from the icon.py file
class CommandThread(QThread):
    output = pyqtSignal(str)
    completed = pyqtSignal()

    def __init__(self, serial_port, command):
        super().__init__()
        self.serial_port = serial_port
        self.command = command

    def run(self):
        if self.serial_port and self.serial_port.isOpen():
            self.serial_port.write((self.command + '\n').encode())
            output = ""
            while True:
                line = self.serial_port.read_until().decode()
                if line.startswith('root@orangepizero:'):
                    break
                if not line.startswith(self.command):
                    output += line
            self.output.emit(output)
        self.completed.emit()

class SerialApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.title = 'ChatMeow配网工具(测试)'
        self.left = 50
        self.top = 50
        self.width = 400
        self.height = 450
        self.serial_port = None
        self.command_thread = None
        self.initUI()

    def initUI(self):

        tray_icon = QSystemTrayIcon(self)
        icon_data = base64.b64decode(icon_data_base64)
        icon = QIcon()
        icon.addPixmap(QPixmap().fromImage(QImage.fromData(icon_data)))
        tray_icon.setIcon(icon)

        self.setWindowTitle(self.title)
        self.setWindowIcon(icon)
        self.setGeometry(self.left, self.top, self.width, self.height)

        widget = QWidget(self)
        self.setCentralWidget(widget)
        layout = QVBoxLayout()

        self.comboBox = QComboBox(self)
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.comboBox.addItem(port.device)
        layout.addWidget(QLabel('选择串口:'))
        layout.addWidget(self.comboBox)

        self.openButton = QPushButton('打开串口连接', self)
        self.openButton.clicked.connect(self.toggle_serial_connection)
        layout.addWidget(self.openButton)

        self.wifiComboBox = QComboBox(self)
        layout.addWidget(QLabel('可用WiFi网络:'))
        layout.addWidget(self.wifiComboBox)

        self.scanButton = QPushButton('扫描WiFi网络', self)
        self.scanButton.clicked.connect(lambda: self.send_command("bash /root/scan_wifi.sh"))
        layout.addWidget(self.scanButton)

        self.connectButton = QPushButton('连接到WiFi', self)
        self.connectButton.clicked.connect(self.connect_wifi)
        layout.addWidget(self.connectButton)

        self.cancelButton = QPushButton('取消当前操作', self)
        self.cancelButton.clicked.connect(self.cancel_command)
        layout.addWidget(self.cancelButton)

        self.connectionStatusLabel = QLabel('未连接到WiFi')
        layout.addWidget(self.connectionStatusLabel)

        self.ipAddressLabel = QLabel('IP地址: 未知')
        layout.addWidget(self.ipAddressLabel)

        # Add a QLabel to display the QR Code
        self.qrCodeLabel = QLabel(self)
        layout.addWidget(self.qrCodeLabel)  # Add the QR code label to the layout

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
            self.scan_wifi()
        except Exception as e:
            QMessageBox.warning(self, '警告', f'无法打开串口：{str(e)}')

    def close_serial_connection(self):
        if self.serial_port:
            self.serial_port.close()
            self.terminal.append("串口已断开")
            self.openButton.setText("打开串口连接")
            self.openButton.setEnabled(True)  # Enable button once connection is closed

    def send_command(self, command):
        if not self.serial_port or not self.serial_port.isOpen():
            QMessageBox.warning(self, '警告', '串口未连接！')
            return
        self.command_thread = CommandThread(self.serial_port, command)
        self.command_thread.output.connect(self.handle_output)
        self.command_thread.completed.connect(self.command_finished)
        self.scanButton.setEnabled(False)  # Disable the scan button during the command
        self.connectButton.setEnabled(False)  # Disable the connect button during the command
        self.command_thread.start()

    def handle_output(self, output):
        self.terminal.append(output)
        if "scan_wifi.sh" in self.command_thread.command:
            self.wifiComboBox.clear()
            for ssid in output.strip().split('\n'):
                if ssid:
                    self.wifiComboBox.addItem(ssid)

    def command_finished(self):
        self.terminal.append("命令执行完成")
        self.update_wifi_status()
        self.scanButton.setEnabled(True)  # Re-enable the scan button after the command
        self.connectButton.setEnabled(True)  # Re-enable the connect button after the command

    def cancel_command(self):
        if self.serial_port and self.serial_port.isOpen():
            self.serial_port.write(b'\x03')
            self.terminal.append("发送取消命令...")
            time.sleep(0.5)
            self.serial_port.reset_input_buffer()
            self.terminal.append("取消命令发送完成")

    def scan_wifi(self):
        self.send_command("bash /root/scan_wifi.sh")

    def connect_wifi(self):
        network_name = self.wifiComboBox.currentText()
        if network_name:
            password, ok = QInputDialog.getText(self, '输入密码', f'输入WiFi密码: {network_name}', QLineEdit.Password)
            if ok:
                self.send_command(f"nmcli dev wifi connect '{network_name}' password '{password}'")

    def update_wifi_status(self):
        if self.serial_port and self.serial_port.isOpen():
            self.command_thread = CommandThread(self.serial_port,
                                                "nmcli -t -f GENERAL.CONNECTION,IP4.ADDRESS device show wlan0 | grep 'GENERAL.CONNECTION\|IP4.ADDRESS' --color=never")
            self.command_thread.output.connect(self.handle_wifi_status)
            self.command_thread.completed.connect(lambda: self.terminal.append("WiFi状态与IP地址更新完成"))
            self.command_thread.start()
        else:
            QMessageBox.warning(self, '警告', '串口未连接！')

    def handle_wifi_status(self, output):
        lines = output.strip().split('\n')
        ssid = ip_address = '未知'
        for line in lines:
            print(line)
            if 'GENERAL.CONNECTION:' in line:
                    ssid = line.split(':', 1)[1].strip()
            elif 'IP4.ADDRESS' in line:
                ip_address = line.split(':', 1)[1].strip().split('/', 1)[0]  # Remove the CIDR notation
                print(ip_address)
        self.connectionStatusLabel.setText(f'已连接到: {ssid}')
        self.ipAddressLabel.setText(f'web服务器: {ip_address}\n使用同一网段的任意设备浏览器\n访问ChatMeow页面，可扫描二维码访问')
        self.update_qr_code(ip_address)  # Update the QR code when the IP address is updated

    def update_qr_code(self, ip_address):
        if ip_address != '未知':
            url = f'http://{ip_address}'
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            # 用 BytesIO 将图像保存到内存中
            byte_array = BytesIO()
            img.save(byte_array, format='PNG')  # 保存为 PNG 格式
            byte_array.seek(0)  # 移动到流的开始

            # 从内存中加载 QPixmap
            pixmap = QPixmap()
            pixmap.loadFromData(byte_array.getvalue())
            self.qrCodeLabel.setPixmap(pixmap)
            self.qrCodeLabel.setAlignment(Qt.AlignCenter)  # 居中显示 QR 码
        else:
            self.qrCodeLabel.clear()  # 清除 QLabel 如果没有有效的 IP 地址


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = SerialApp()
    ex.show()
    sys.exit(app.exec_())
