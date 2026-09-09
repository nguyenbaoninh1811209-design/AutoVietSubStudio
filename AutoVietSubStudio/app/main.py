from pathlib import Path
import sys, logging
from PySide6.QtWidgets import QApplication
from app.ui.main_window import MainWindow

def main():
    root=Path(__file__).resolve().parents[1]/'data'
    root.mkdir(exist_ok=True)
    logging.basicConfig(filename=root/'logs'/'app.log',level=logging.INFO,encoding='utf-8',format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    app=QApplication(sys.argv)
    app.setApplicationName('AutoVietSub Studio')
    w=MainWindow(root); w.show()
    sys.exit(app.exec())
if __name__=='__main__': main()
