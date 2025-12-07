import sys
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QSlider,
                             QFileDialog, QComboBox, QMessageBox)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap, QImage
import fitz  # PyMuPDF
from docx import Document
from docx.shared import Inches
import tempfile
from PIL import Image
import io


class DocumentPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_page = 0
        self.total_pages = 0
        self.pages = []
        self.is_playing = False
        self.play_speed = 3000  # 默认3秒/页
        self.loop_enabled = False  # 循环播放
        self.timer = QTimer()
        self.timer.timeout.connect(self.next_page)

        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('文档自动播放器')
        self.setGeometry(100, 100, 1200, 800)

        # 主窗口部件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        # 主布局
        layout = QVBoxLayout()

        # 文档显示区域
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: white;")
        self.image_label.setScaledContents(False)
        layout.addWidget(self.image_label, stretch=1)

        # 控制面板
        self.control_panel = self.create_control_panel()
        layout.addWidget(self.control_panel)

        main_widget.setLayout(layout)

    def create_control_panel(self):
        panel = QWidget()
        panel.setStyleSheet("background-color: #f0f0f0; padding: 10px;")
        layout = QHBoxLayout()

        # 打开文件按钮
        self.open_btn = QPushButton('打开文件')
        self.open_btn.clicked.connect(self.open_file)
        layout.addWidget(self.open_btn)

        # 播放/暂停按钮
        self.play_btn = QPushButton('播放')
        self.play_btn.clicked.connect(self.toggle_play)
        self.play_btn.setEnabled(False)
        layout.addWidget(self.play_btn)

        # 上一页按钮
        self.prev_btn = QPushButton('上一页')
        self.prev_btn.clicked.connect(self.prev_page)
        self.prev_btn.setEnabled(False)
        layout.addWidget(self.prev_btn)

        # 下一页按钮
        self.next_btn = QPushButton('下一页')
        self.next_btn.clicked.connect(self.next_page)
        self.next_btn.setEnabled(False)
        layout.addWidget(self.next_btn)

        # 页码显示
        self.page_label = QLabel('0 / 0')
        layout.addWidget(self.page_label)

        # 速度选择
        layout.addWidget(QLabel('播放速度:'))
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(['1秒/页', '2秒/页', '3秒/页', '5秒/页', '10秒/页'])
        self.speed_combo.setCurrentIndex(2)  # 默认3秒
        self.speed_combo.currentIndexChanged.connect(self.change_speed)
        layout.addWidget(self.speed_combo)

        # 全屏按钮
        self.fullscreen_btn = QPushButton('全屏')
        self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)
        layout.addWidget(self.fullscreen_btn)

        # 循环播放按钮
        self.loop_btn = QPushButton('循环:关')
        self.loop_btn.clicked.connect(self.toggle_loop)
        layout.addWidget(self.loop_btn)

        panel.setLayout(layout)
        return panel

    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, '选择文档', '',
            'Documents (*.pdf *.docx);;PDF Files (*.pdf);;Word Files (*.docx)'
        )

        if file_path:
            self.load_document(file_path)

    def load_document(self, file_path):
        try:
            self.pages = []

            if file_path.lower().endswith('.pdf'):
                self.load_pdf(file_path)
            elif file_path.lower().endswith('.docx'):
                self.load_word(file_path)
            else:
                QMessageBox.warning(self, '错误', '不支持的文件格式')
                return

            if self.pages:
                self.total_pages = len(self.pages)
                self.current_page = 0
                self.display_current_page()
                self.update_controls()
                QMessageBox.information(self, '成功', f'加载了 {self.total_pages} 页')
            else:
                QMessageBox.warning(self, '错误', '无法加载文档')

        except Exception as e:
            QMessageBox.critical(self, '错误', f'加载文档失败: {str(e)}')

    def load_pdf(self, file_path):
        # 使用 PyMuPDF 读取 PDF
        doc = fitz.open(file_path)
        self.pages = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=200)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            self.pages.append(img)
        doc.close()

    def load_word(self, file_path):
        # Word文档暂不支持
        QMessageBox.information(
            self, '提示',
            'Word 文档暂不支持直接加载。\n\n建议：\n1. 将 Word 文档另存为 PDF\n2. 然后用本程序打开 PDF 文件'
        )

    def display_current_page(self):
        if 0 <= self.current_page < len(self.pages):
            # 将PIL图片转换为QPixmap
            pil_image = self.pages[self.current_page]

            # 转换为QImage
            img_byte_arr = io.BytesIO()
            pil_image.save(img_byte_arr, format='PNG')
            img_byte_arr = img_byte_arr.getvalue()

            qimage = QImage()
            qimage.loadFromData(img_byte_arr)

            pixmap = QPixmap.fromImage(qimage)

            # 缩放以适应窗口
            scaled_pixmap = pixmap.scaled(
                self.image_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

            self.image_label.setPixmap(scaled_pixmap)
            self.page_label.setText(f'{self.current_page + 1} / {self.total_pages}')

    def next_page(self):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.display_current_page()
        else:
            # 到达最后一页
            if self.loop_enabled:
                # 循环播放，回到第一页
                self.current_page = 0
                self.display_current_page()
            else:
                # 停止播放
                if self.is_playing:
                    self.toggle_play()

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.display_current_page()

    def toggle_play(self):
        if not self.pages:
            return

        self.is_playing = not self.is_playing

        if self.is_playing:
            self.play_btn.setText('暂停')
            self.timer.start(self.play_speed)
        else:
            self.play_btn.setText('播放')
            self.timer.stop()

    def change_speed(self):
        speed_map = {
            0: 1000,  # 1秒
            1: 2000,  # 2秒
            2: 3000,  # 3秒
            3: 5000,  # 5秒
            4: 10000  # 10秒
        }
        self.play_speed = speed_map[self.speed_combo.currentIndex()]

        # 如果正在播放，重新启动定时器
        if self.is_playing:
            self.timer.stop()
            self.timer.start(self.play_speed)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.fullscreen_btn.setText('全屏')
            self.control_panel.show()  # 退出全屏时显示控制面板
        else:
            self.showFullScreen()
            self.fullscreen_btn.setText('退出全屏')
            self.control_panel.hide()  # 全屏时隐藏控制面板

    def toggle_loop(self):
        """切换循环播放"""
        self.loop_enabled = not self.loop_enabled
        if self.loop_enabled:
            self.loop_btn.setText('循环:开')
        else:
            self.loop_btn.setText('循环:关')

    def update_controls(self):
        has_pages = len(self.pages) > 0
        self.play_btn.setEnabled(has_pages)
        self.prev_btn.setEnabled(has_pages)
        self.next_btn.setEnabled(has_pages)

    def keyPressEvent(self, event):
        # 键盘快捷键
        if event.key() == Qt.Key_F11:
            self.toggle_fullscreen()
        elif event.key() == Qt.Key_Space:
            if self.pages:
                self.toggle_play()
        elif event.key() == Qt.Key_Left:
            self.prev_page()
        elif event.key() == Qt.Key_Right:
            self.next_page()
        elif event.key() == Qt.Key_Escape:
            if self.isFullScreen():
                self.toggle_fullscreen()
        elif event.key() == Qt.Key_L:
            self.toggle_loop()

    def mousePressEvent(self, event):
        """处理鼠标点击事件"""
        if event.button() == Qt.RightButton:
            # 右键点击时切换控制面板显示/隐藏
            if self.control_panel.isVisible():
                self.control_panel.hide()
            else:
                self.control_panel.show()

    def resizeEvent(self, event):
        # 窗口大小改变时重新显示当前页
        super().resizeEvent(event)
        if self.pages:
            self.display_current_page()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    player = DocumentPlayer()
    player.show()
    sys.exit(app.exec_())