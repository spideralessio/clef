from clef_app.gui.main_window import MainApp
from clef_app.logging_setup import setup_logging

if __name__ == "__main__":
    setup_logging()
    app = MainApp()
    app.mainloop()
