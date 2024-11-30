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
            progress_callback(f"다운로드 중에 문제가 생겼어요: {e} 미이~")
        raise e


# ZIP 파일 압축 해제
def extract_zip(zip_path, extract_to, progress_callback=None):
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_to)
    except zipfile.BadZipFile:
        if progress_callback:
            progress_callback("압축 파일이 망가진 것 같아요. 슬퍼요~")
        raise
    except Exception as e:
        if progress_callback:
            progress_callback(f"압축을 푸는 중에 문제가 생겼어요: {e} 도와주세요~")
        raise


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
                "구글 드라이브에서 패치 파일을 가져오는 중이에요. 조금만 기다려 주세요~"
            )
        download_from_google_drive(file_id, zip_path, progress_callback)
        if progress_callback:
            progress_callback(f"다운로드가 끝났어요! 저장된 곳은 여기에요: {zip_path}")

        # 2. ZIP 파일 압축 해제
        if progress_callback:
            progress_callback("패치 파일을 풀고 있어요. 미이~")
        extract_zip(zip_path, temp_dir, progress_callback)
        if progress_callback:
            progress_callback(f"압축을 다 풀었어요! 여기로 풀렸어요: {temp_dir}")

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
                    "문제가 생겼어요! 패치 파일 안에서 'Data' 폴더를 못 찾았어요. 패치를 적용할 수 없어요. 미이~"
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
                    "어라? '한국어 패치' 폴더가 안 보여요. 그래서 패치를 적용할 수 없어요. 미안해요~"
                )
                return False
            # 모든 파일 복사
            all_items = [p for p in korean_patch_folder.rglob("*") if p.is_file()]

        # 5. 총 파일 수를 기반으로 진행률 표시하며 복사
        progress_callback("패치 파일을 적용하는 중이에요. 조금만 기다려 주세요~")
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
                    f"파일을 복사하는 중 문제가 생겼어요: {file_path} -> {target_path}\n오류 메시지: {e} 도와주세요~"
                )
        progress_callback(
            f"패치를 다 적용했어요! 대상 경로는 이거예요: {destination} 니파~☆"
        )
        return True  # 패치 성공


# GUI 설정
class PatchInstallerUI:
    def __init__(self, root, chapters, library_paths):
        self.root = root
        self.root.title("쓰르라미 울 적에 한글 패치 마법사")
        self.root.geometry("700x750")  # 창 크기 조정
        self.library_paths = library_paths

        self.selected_chapters = []
        self.chapters = chapters

        # 기본 폰트 설정 (맑은 고딕 사용)
        self.custom_font = ("맑은 고딕", 12)

        # 이미지 추가 (이미지 크기 조정 포함)
        try:
            image_path = r"IMG.png"
            self.header_image = Image.open(image_path)
            # 이미지 크기 조정 (너무 크다면 줄여줌)
            self.header_image = self.header_image.resize((300, 400), Image.LANCZOS)
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
            text="어떤 챕터에 패치를 적용할지 골라주세요~",
            justify="center",
            font=self.custom_font,
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
        self.status_label = ttk.Label(self.root, text="", font=self.custom_font)
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
                "경고", "에? 설치할 챕터를 하나도 안 골랐어요! 골라 주세요~"
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
                    f"{display_name} 폴더를 찾을 수가 없네요. 이건 건너뛰어야 할 것 같아요. 미이~"
                )
                continue

            self.update_status(
                f"{display_name}의 설치 경로를 찾았어요! 여기예요: {game_path}"
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
                    f"{display_name}에 패치를 적용하는 중 문제가 생겼어요: {e} 도와주세요~"
                )

        # 결과 표시
        if patched_chapters:
            messagebox.showinfo(
                "완료",
                "다음 챕터에 한글 패치가 잘 적용되었어요!\n"
                + "\n".join(patched_chapters)
                + "\n니파~☆",
            )
        else:
            messagebox.showinfo("완료", "패치가 적용된 챕터가 하나도 없네요... 슬퍼요~")


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
        messagebox.showerror("오류", "Steam 설치 경로를 찾지 못했어요. 미이~")
        exit()

    # Steam 라이브러리 폴더 찾기
    library_paths = get_steam_library_folders(steam_path)
    if not library_paths:
        messagebox.showerror("오류", "Steam 라이브러리 폴더가 보이지 않아요.")
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
