import os
import sys
import webbrowser
from pathlib import Path

def _add_src_to_syspath(base_dir: Path) -> None:
    candidates = [
        base_dir / "src",
        base_dir / "_internal" / "src",
        Path(getattr(sys, "_MEIPASS", "")) / "src" if hasattr(sys, "_MEIPASS") else None,  # onefile [1](https://stackoverflow.com/questions/51060894/adding-a-data-file-in-pyinstaller-using-the-onefile-option)
    ]
    for p in candidates:
        if p and p.exists():
            sys.path.insert(0, str(p))
            return

def main():
    # base_dir: en onedir es dist\descarga-pml; en onefile es sys._MEIPASS (temp) [1](https://stackoverflow.com/questions/51060894/adding-a-data-file-in-pyinstaller-using-the-onefile-option)
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    os.chdir(base_dir)

    _add_src_to_syspath(base_dir)

    # tu app está dentro del bundle; en onedir normalmente estará en _internal/app
    app_candidates = [
        base_dir / "app" / "streamlit_app.py",
        base_dir / "_internal" / "app" / "streamlit_app.py",
        Path(getattr(sys, "_MEIPASS", "")) / "app" / "streamlit_app.py" if hasattr(sys, "_MEIPASS") else None,
    ]
    app_path = next((p for p in app_candidates if p and p.exists()), None)
    if not app_path:
        raise FileNotFoundError("No se encontró streamlit_app.py dentro del bundle")

    from streamlit.web import cli as stcli  # patrón para ejecutar Streamlit desde código [2](https://stackoverflow.com/questions/65357245/turn-streamlit-application-into-a-pyinstaller-executable)[3](https://github.com/emsignailgnehs/Tutorial_Pyinstaller_for_Streamlit)

    port = "8501"
    sys.argv = [
        "streamlit",
        "run",
        str(app_path),
        "--server.headless=true",
        f"--server.port={port}",
        "--global.developmentMode=false",
    ]

    webbrowser.open(f"http://localhost:{port}")
    sys.exit(stcli.main())

if __name__ == "__main__":
    main()