import os

def test_source_files_exist():
    for p in ['radar_core.py','run_worker.py','radar_desktop.py','build_windows.ps1','installer/Radar.iss']:
        assert os.path.exists(p)

def test_python_compile():
    for p in ['radar_core.py','run_worker.py','radar_desktop.py']:
        compile(open(p,encoding='utf-8').read(),p,'exec')
