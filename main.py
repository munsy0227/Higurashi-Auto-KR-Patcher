import shutil
import zipfile
from pathlib import Path
import gdown
import re
import tempfile
from tqdm import tqdm
import os
import tkinter as tk
from tkinter import ttk, messagebox
import vdf
import threading
from PIL import Image, ImageTk
import sys
import sv_ttk
import winreg


# Windows 다크 모드 감지 함수
def is_windows_dark_mode():
    try:
        registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        key = winreg.OpenKey(registry, key_path)
        # 'AppsUseLightTheme' 값이 0이면 다크 모드, 1이면 라이트 모드
        use_light_theme = winreg.QueryValueEx(key, "AppsUseLightTheme")[0]
        winreg.CloseKey(key)
        return use_light_theme == 0
    except Exception as e:
        print(f"다크 모드 감지 중 오류 발생: {e}")
        return False  # 오류 발생 시 기본적으로 라이트 모드로 간주


# Steam 설치 경로 가져오기
def get_steam_install_path():
    import winreg

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        steam_path, _ = winreg.QueryValueEx(key, "SteamPath")
        return steam_path
    except FileNotFoundError:
        return None


# Steam 라이브러리 폴더 가져오기
def get_steam_library_folders(steam_path):
    library_file = Path(steam_path) / "config/libraryfolders.vdf"
    if not library_file.exists():
        return []

    try:
        with open(library_file, "r", encoding="utf-8") as file:
            data = vdf.load(file)
        libraries = []
        for item in data.get("libraryfolders", {}):
            if item.isdigit():
                path = data["libraryfolders"][item].get("path")
                if path:
                    libraries.append(path)
        # Steam 설치 경로도 라이브러리 경로에 포함
        libraries.append(steam_path)
        return libraries
    except Exception as e:
        print(f"'libraryfolders.vdf' 파일을 파싱하는 중 오류 발생: {e}")
        return []


# 게임 폴더 이름을 기준으로 설치 경로 확인
def find_game_install_path_by_name(library_paths, folder_name):
    for library in library_paths:
        potential_path = Path(library) / f"steamapps/common/{folder_name}"
        if potential_path.exists():
            return potential_path
    return None


# Google Drive에서 파일 다운로드
def download_from_google_drive(file_id, destination, progress_callback=None):
    url = f"https://drive.google.com/uc?id={file_id}"
    try:
        gdown.download(url, str(destination), quiet=False)
    except Exception as e:
        if progress_callback:
            progress_callback(f"다운로드 중 문제가 발생하였습니다: {e}")
        raise e


# ZIP 파일 압축 해제
def extract_zip(zip_path, extract_to, progress_callback=None):
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_to)
    except zipfile.BadZipFile:
        if progress_callback:
            progress_callback("압축 파일이 손상된 것 같습니다.")
        raise
    except Exception as e:
        if progress_callback:
            progress_callback(f"압축 해제 중 문제가 발생하였습니다: {e}")
        raise


# 리소스 파일 접근을 위한 경로 설정 함수
def resource_path(relative_path):
    """PyInstaller로 패키징된 파일 내부의 리소스 경로를 얻습니다."""
    if hasattr(sys, "_MEIPASS"):
        # PyInstaller로 패키징된 경우 임시 디렉터리 경로 반환
        return Path(sys._MEIPASS) / relative_path
    else:
        # 일반 Python 스크립트 실행 시
        return Path(relative_path)


# ZIP 파일을 다운로드하고 압축 해제 및 복사
def apply_patch_from_zip(
    file_id, destination, progress_callback=None, special_handling=False
):
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        zip_path = temp_dir / "patch.zip"

        # 1. ZIP 파일 다운로드
        if progress_callback:
            progress_callback(
                "구글 드라이브에서 패치 파일을 가져오는 중입니다. 잠시만 기다려 주시기 바랍니다."
            )
        download_from_google_drive(file_id, zip_path, progress_callback)
        if progress_callback:
            progress_callback(
                f"다운로드가 완료되었습니다. 저장된 위치는 다음과 같습니다: {zip_path}"
            )

        # 2. ZIP 파일 압축 해제
        if progress_callback:
            progress_callback("패치 파일을 해제하는 중입니다.")
        extract_zip(zip_path, temp_dir, progress_callback)
        if progress_callback:
            progress_callback(
                f"압축이 모두 해제되었습니다. 해제된 위치는 다음과 같습니다: {temp_dir}"
            )

        if special_handling:
            # 동적으로 'Data' 폴더 찾기
            data_folder = next(
                (
                    Path(root) / "Data"
                    for root, dirs, files in os.walk(temp_dir)
                    if "Data" in dirs
                ),
                None,
            )
            if not data_folder:
                progress_callback(
                    "패치 파일 내에서 'Data' 폴더를 찾을 수 없어 적용이 불가능합니다."
                )
                return False
            # 모든 파일 복사
            all_items = [p for p in data_folder.rglob("*") if p.is_file()]
        else:
            # 일반 처리: 한글 패치 폴더를 동적으로 찾기
            korean_patch_folder = next(
                (
                    item
                    for item in temp_dir.iterdir()
                    if item.is_dir() and "패치" in item.name
                ),
                None,
            )
            if korean_patch_folder is None:
                progress_callback(
                    "'한국어 패치' 폴더를 확인할 수 없어 패치를 적용할 수 없습니다."
                )
                return False
            # 모든 파일 복사
            all_items = [p for p in korean_patch_folder.rglob("*") if p.is_file()]

        # 5. 총 파일 수를 기반으로 진행률 표시하며 복사
        progress_callback("패치 파일을 적용하고 있습니다. 잠시만 기다려 주십시오.")
        for file_path in tqdm(all_items, desc="패치 적용", unit="file"):
            relative_path = file_path.relative_to(
                data_folder if special_handling else korean_patch_folder
            )
            target_path = destination / relative_path

            # 대상 디렉터리가 없으면 생성
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # 파일 복사
            try:
                shutil.copy2(file_path, target_path)
            except Exception as e:
                progress_callback(
                    f"파일 복사 중 문제가 발생하였습니다: {file_path} -> {target_path}\n오류: {e}"
                )
        progress_callback(
            f"패치가 완료되었습니다. 적용된 경로는 다음과 같습니다: {destination}"
        )
        return True  # 패치 성공


# Steamgrid 이미지 적용
def apply_steamgrid_images(steam_path):
    # 사용자 데이터 경로
    user_data_dir = Path(steam_path) / "userdata"
    steamgrid_source = resource_path("Steamgrid")

    if not steamgrid_source.exists():
        print(f"Error: Steamgrid 이미지를 찾을 수 없습니다. 경로: {steamgrid_source}")
        return

    # 각 사용자의 Steamgrid 이미지 경로에 이미지 복사
    for user_dir in user_data_dir.iterdir():
        if user_dir.is_dir():
            grid_destination = user_dir / "config" / "grid"
            grid_destination.mkdir(parents=True, exist_ok=True)

            for image_file in steamgrid_source.glob("*.*"):
                target_image_path = grid_destination / image_file.name
                try:
                    shutil.copy2(image_file, target_image_path)
                except Exception as e:
                    print(
                        f"이미지 복사 중 오류 발생: {image_file} -> {target_image_path}, 오류 메시지: {e}"
                    )

    print(
        f"모든 Steamgrid 이미지가 해당 경로에 복사되었습니다: {user_data_dir}/config/grid"
    )


# GUI 설정
class PatchInstallerUI:
    def __init__(self, root, chapters, library_paths):
        self.root = root
        self.root.title("쓰르라미 울 적에 한글 패치 마법사")
        self.root.geometry("750x500")  # 창 크기 조정
        self.library_paths = library_paths

        # 다크 모드 여부 감지
        self.is_dark_mode = is_windows_dark_mode()

        # Sun Valley 테마 적용
        sv_ttk.set_theme("dark" if self.is_dark_mode else "light")

        # 기본 폰트 설정 (맑은 고딕 사용)
        self.custom_font = ("맑은 고딕", 12)

        # ttk 스타일에 기본 폰트 적용
        style = ttk.Style()
        style.configure(".", font=self.custom_font)
        style.configure("TLabel", font=self.custom_font)
        style.configure("TButton", font=self.custom_font)
        style.configure("TCheckbutton", font=self.custom_font)

        self.selected_chapters = []
        self.chapters = chapters

        # 이미지 추가 (이미지 크기 조정 포함)
        try:
            image_path = resource_path("IMG.png")
            self.header_image = Image.open(image_path)
            # 이미지 크기 조정 (너무 크다면 줄여줌)
            self.header_image = self.header_image.resize((500, 163), Image.LANCZOS)
            self.header_image_tk = ImageTk.PhotoImage(self.header_image)

            # 이미지 레이블 생성
            header_label = tk.Label(self.root, image=self.header_image_tk)
            header_label.pack(pady=10)
        except Exception as e:
            print(f"이미지 로드 중 오류 발생: {e}")

        self.create_widgets()

    def create_widgets(self):
        # 제목 레이블
        title_label = ttk.Label(
            self.root,
            text="어떤 챕터에 패치를 적용할지 선택해 주십시오.",
            justify="center",
        )
        title_label.pack(pady=10)

        # 체크 버튼 목록 (세 개의 열로 나눔)
        self.chapter_vars = []

        # 체크 버튼들을 담을 프레임을 중앙에 배치
        main_frame = ttk.Frame(self.root)
        main_frame.pack(pady=20)

        # 첫 번째 열 (첫 4개 챕터)
        first_column_frame = ttk.Frame(main_frame)
        first_column_frame.grid(row=0, column=0, padx=20, sticky="n")

        for idx in range(4):
            var = tk.BooleanVar(value=self.chapters[idx].get("installed", False))
            self.chapter_vars.append(var)
            chk = ttk.Checkbutton(
                first_column_frame,
                text=self.chapters[idx]["display_name"],
                variable=var,
            )
            chk.pack(anchor="w")

        # 두 번째 열 (다음 4개 챕터)
        second_column_frame = ttk.Frame(main_frame)
        second_column_frame.grid(row=0, column=1, padx=20, sticky="n")

        for idx in range(4, 8):
            var = tk.BooleanVar(value=self.chapters[idx].get("installed", False))
            self.chapter_vars.append(var)
            chk = ttk.Checkbutton(
                second_column_frame,
                text=self.chapters[idx]["display_name"],
                variable=var,
            )
            chk.pack(anchor="w")

        # 세 번째 열 (나머지 챕터)
        third_column_frame = ttk.Frame(main_frame)
        third_column_frame.grid(row=0, column=2, padx=20, sticky="n")

        for idx in range(8, len(self.chapters)):
            var = tk.BooleanVar(value=self.chapters[idx].get("installed", False))
            self.chapter_vars.append(var)
            chk = ttk.Checkbutton(
                third_column_frame,
                text=self.chapters[idx]["display_name"],
                variable=var,
            )
            chk.pack(anchor="w")

        # 진행 상태 표시 레이블
        self.status_label = ttk.Label(self.root, text="")
        self.status_label.pack(pady=20)

        # 설치 버튼
        install_btn = ttk.Button(
            self.root, text="한글 패치 설치", command=self.start_installation_thread
        )
        install_btn.pack(pady=10)

    def update_status(self, message):
        self.status_label.config(text=message)
        self.root.update_idletasks()

    def start_installation_thread(self):
        # 설치 작업을 별도의 스레드에서 실행
        install_thread = threading.Thread(target=self.start_installation)
        install_thread.start()

    def start_installation(self):
        # 선택된 챕터 수집
        self.selected_chapters = [
            self.chapters[idx] for idx, var in enumerate(self.chapter_vars) if var.get()
        ]

        if not self.selected_chapters:
            messagebox.showwarning(
                "경고",
                "설치할 챕터를 선택하지 않으셨습니다. 챕터를 선택해 주시기 바랍니다.",
            )
            return

        # 패치 설치 시작
        patched_chapters = []

        for chapter in self.selected_chapters:
            folder_name = chapter["name"]
            display_name = chapter["display_name"]
            game_path = find_game_install_path_by_name(self.library_paths, folder_name)
            if not game_path:
                self.update_status(
                    f"{display_name} 폴더를 찾을 수 없어 건너뛰었습니다."
                )
                continue

            self.update_status(
                f"{display_name}의 설치 경로를 확인하였습니다. 경로: {game_path}"
            )

            try:
                special_handling = chapter.get("special_handling", False)
                success = apply_patch_from_zip(
                    chapter["google_drive_id"],
                    game_path,
                    self.update_status,
                    special_handling,
                )
                if success:
                    patched_chapters.append(display_name)
            except Exception as e:
                self.update_status(
                    f"{display_name}에 패치 적용 중 문제가 발생하였습니다: {e}"
                )

        # 결과 표시
        if patched_chapters:
            messagebox.showinfo(
                "완료",
                "다음 챕터에 한글 패치가 성공적으로 적용되었습니다.\n"
                + "\n".join(patched_chapters),
            )
        else:
            messagebox.showinfo("완료", "패치가 적용된 챕터가 없습니다.")


# 메인 실행
if __name__ == "__main__":
    # 챕터 정보
    chapters = [
        {
            "name": "Higurashi When They Cry",
            "display_name": "오니카쿠시 편 (챕터 1)",
            "google_drive_id": "1J2FmtLdf72iU0M8PY7WE6L_DVU2ziw3S",
        },
        {
            "name": "Higurashi 02 - Watanagashi",
            "display_name": "와타나가시 편 (챕터 2)",
            "google_drive_id": "1KrEgh4CvKDP4DPulR3GIqGo_Ms1ciCkm",
        },
        {
            "name": "Higurashi 03 - Tatarigoroshi",
            "display_name": "타타리고로시 편 (챕터 3)",
            "google_drive_id": "1XFiYcOQt41s57GKPsLbrC8kblJwHG2D5",
        },
        {
            "name": "Higurashi 04 - Himatsubushi",
            "display_name": "히마츠부시 편 (챕터 4)",
            "google_drive_id": "1Z6SJLRZO8KkYIQs_C3BVnWfaWWrL4poa",
        },
        {
            "name": "Higurashi When They Cry Hou - Ch. 5 Meakashi",
            "display_name": "메아카시 편 (챕터 5)",
            "google_drive_id": "1K25opRd1HtJGWLl9DWzcsvWMKqaZaU_P",
        },
        {
            "name": "Higurashi When They Cry Hou - Ch.6 Tsumihoroboshi",
            "display_name": "츠미호로보시 편 (챕터 6)",
            "google_drive_id": "1si3l8EYlZFfI8DVtpJT4WAY_I0VEEnEz",
        },
        {
            "name": "Higurashi When They Cry Hou - Ch.7 Minagoroshi",
            "display_name": "미나고로시 편 (챕터 7)",
            "google_drive_id": "1AsbW4Oozy76YySHRIQT0sp3rSejryDp8",
        },
        {
            "name": "Higurashi When They Cry Hou - Ch.8 Matsuribayashi",
            "display_name": "마츠리바야시 편 (챕터 8)",
            "google_drive_id": "1si3l8EYlZFfI8DVtpJT4WAY_I0VEEnEz",
        },
        {
            "name": "Higurashi When They Cry Hou - Rei",
            "display_name": "쓰르라미 울 적에 례",
            "google_drive_id": "13wdP3jz5FvaVi0PBZ_6WsiCK591VkEYS",
        },
        {
            "name": "Higurashi When They Cry Hou+",
            "display_name": "쓰르라미 울 적에 봉+",
            "google_drive_id": "1kAA5JDB-gFa_mEglHqAvvt8SFV7s3Npb",
            "special_handling": True,
        },
    ]

    # Steam 설치 경로 찾기
    steam_path = get_steam_install_path()
    if not steam_path:
        messagebox.showerror("오류", "Steam 설치 경로를 확인할 수 없습니다.")
        exit()

    # Steam 라이브러리 폴더 찾기
    library_paths = get_steam_library_folders(steam_path)
    if not library_paths:
        messagebox.showerror("오류", "Steam 라이브러리 폴더를 찾을 수 없습니다.")
        exit()

    # 설치된 챕터 자동 감지
    for chapter in chapters:
        folder_name = chapter["name"]
        game_path = find_game_install_path_by_name(library_paths, folder_name)
        chapter["installed"] = game_path is not None

    # UI 생성
    root = tk.Tk()
    app = PatchInstallerUI(root, chapters, library_paths)
    root.mainloop()

    # 패치 설치 후 Steamgrid 이미지 적용
    apply_steamgrid_images(steam_path)
