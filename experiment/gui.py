"""Tkinter launcher for the supervisor running a session.

Shows a small configuration form pre-filled with the previously used
values (``configs/.last_used.yaml``), so repeat sessions only require
tweaking the participant ID and pressing Apply. On Apply, the window
hides itself and launches the participant-facing pygame screen
(``experiment.main``) as a subprocess; it reappears automatically once
that process exits, and shows the psychometric fit for that session
(from the freshly saved trial CSV) directly in the panel.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Iterable

import yaml
from PIL import Image, ImageTk

from .config import ExperimentConfig, config_to_dict, load_experiment_config

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIGS_DIR = Path(__file__).resolve().parent / "configs"
DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_CONFIG_PATH = CONFIGS_DIR / "default.yaml"
LAST_USED_PATH = CONFIGS_DIR / ".last_used.yaml"

# (attribute, Turkish label, kind) -- kind in {"float", "int", "optional_int", "bool", "mode", "str"}
FIELD_GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ("Katılımcı ve Mod", [
        ("participant_id", "Katılımcı ID", "str"),
        ("mode", "Mod", "mode"),
    ]),
    ("Uyaran Geometrisi (mm)", [
        ("base_height_mm", "Referans yükseklik", "float"),
        ("bar_width_mm", "Çubuk genişliği", "float"),
        ("inter_bar_gap_mm", "Çubuklar arası boşluk", "float"),
    ]),
    ("Sabit Uyaranlar Tasarımı", [
        ("delta_max_pct", "Maks. fark oranı (delta_max_pct)", "float"),
        ("n_levels", "Seviye sayısı", "int"),
        ("include_zero_level", "0% seviyeyi dahil et", "bool"),
        ("trials_per_level", "Seviye başına deneme", "int"),
        ("catch_trial_pct", "Kontrol deneme oranı", "float"),
    ]),
    ("Görev Ayarları", [
        ("feedback", "Geri bildirim ver", "bool"),
        ("n_practice_trials", "Alıştırma deneme sayısı", "int"),
        ("break_every_n_trials", "Kaç denemede bir mola", "int"),
        ("blind_test_mode", "Kör test modu (çubukları gösterme)", "bool"),
    ]),
    ("Donanım / İşleme", [
        ("carrier_freq_hz", "Taşıyıcı frekans (Hz)", "float"),
        ("voltage_peak", "Tepe voltaj (Vpp)", "float"),
        ("ir_sample_hz_nominal", "IR frame örnekleme (Hz)", "float"),
        ("rng_seed", "RNG seed (boş = rastgele)", "optional_int"),
    ]),
    ("Staircase Pilot (sadece pilot modda)", [
        ("staircase_dh_start_pct", "Başlangıç adımı (%)", "float"),
        ("staircase_dh_min_pct", "Minimum adım (%)", "float"),
        ("staircase_dh_step_pct", "Adım büyüklüğü (%)", "float"),
        ("staircase_n_reversals", "Ters dönüş sayısı", "int"),
        ("staircase_n_reversals_averaged", "Ortalanan ters dönüş", "int"),
    ]),
]

MODE_CHOICES = ["constant_stimuli", "staircase_pilot"]

# Explanation shown under each field. Where the default traces to something
# concrete (a cited standard/paper, or the rig's actual hardware spec, both
# already documented in experiment/README.md and config.py), that source is
# named directly. Where it doesn't -- most of the task/design numbers below --
# this says so plainly, rather than inventing a citation: those are ordinary
# engineering judgment calls the supervisor is expected to tune per session.
FIELD_HELP: dict[str, str] = {
    "participant_id": "Oturumun katılımcı kodu (ör. P01). Kaydedilen dosya adlarında ve CSV'lerde kullanılır.",
    "mode": "constant_stimuli: ana sabit-uyaranlar bloğu. staircase_pilot: delta_max_pct aralığını "
    "belirlemeden önce yaklaşık JND'yi bulmak için hızlı 1-yukarı/2-aşağı adaptif staircase.",
    "base_height_mm": "Referans çubuğun yüksekliği. Karşılaştırma yükseklikleri bunun etrafında "
    "±delta_max_pct ile üretilir; oturum başına sabit tutulan bir tasarım parametresi (bkz. "
    "experiment/README.md: 'One base height ... fixed per session').",
    "bar_width_mm": "Referans ve karşılaştırma çubukları için ortak genişlik. Belirli bir referansa "
    "bağlı değil; Sun ve ark. (2023) elektroadhezyon cihazlarında algılanan minimum çizgi genişliğini "
    "inceliyor, bu değeri seçerken o çalışmaya bakılabilir.",
    "inter_bar_gap_mm": "Çubuklar arası boşluk, >=3.0 mm zorunlu -- bu doğrudan BANA 3.4.3.13 taktil "
    "grafik standardından ve Tang & Beebe (1998)'in çubuklar arası boşluk taban çizgisinden geliyor "
    "(config.py'deki doğrulama kuralına bakın).",
    "delta_max_pct": "En uç karşılaştırma seviyesinin referansa göre yüzde farkı (±); seviyeler bu "
    "değerin negatifinden pozitifine eşit aralıklarla üretilir. Belirli bir makaleye dayanmıyor -- "
    "staircase_pilot modunda bulunan yaklaşık JND'nin ~1.5 katı civarı önerilir (pilot_range_check "
    "uyarısına bakın); supervisor her oturumda ayarlar.",
    "n_levels": "delta_max_pct aralığında kaç eşit aralıklı seviye kullanılacağı. Varsayılan 6, "
    "klasik sabit-uyaranlar yönteminde tipik olan 5-9 seviye aralığında pratik bir seçim -- bu "
    "depoda spesifik bir referansa bağlı değil.",
    "include_zero_level": "0% (referansla birebir aynı) seviyeyi de dahil et. Varsayılan kapalı: "
    "0 farkta 'doğru' cevap tanımsız (şans düzeyinde) olduğundan genelde dışarıda bırakılır.",
    "trials_per_level": "Her seviyede yapılacak deneme sayısı. Varsayılan 10: fit_psychometric.py'nin "
    "tercih ettiği psignifit (Bayesci) yöntemi, kendi belgelemesine göre saniyede ~10 deneme/seviye "
    "ile bile makul güven aralıkları verebiliyor.",
    "catch_trial_pct": "En uç seviyelerde (±delta_max_pct) eklenen ekstra 'kolay' kontrol denemesi "
    "oranı; katılımcının dikkatini/lapse oranını ölçmek içindir. Standart bir dikkat kontrolü "
    "pratiğidir, belirli bir referansa dayanmıyor.",
    "feedback": "Katılımcıya her denemeden sonra doğru/yanlış bildirilsin mi. Ana blokta genelde "
    "kapalı tutulur ki yanıt yanlılığı oluşmasın; alıştırma denemelerinde ayrıca açık çalıştırılır.",
    "n_practice_trials": "Ana bloktan önce katılımcının göreve alışması için yapılan (geri bildirimli) "
    "deneme sayısı. Mühendislik tercihi, belirli bir referansa bağlı değil.",
    "break_every_n_trials": "Kaç denemede bir zorunlu mola verileceği; yorgunluk ve dikkat kaybını "
    "azaltmak içindir. Belirli bir referansa bağlı değil.",
    "blind_test_mode": "Dokunulacak iki sütun tam ekran yüksekliğinde beyaz şeritlerle işaretlenir "
    "(konumlarını bulmak kör bir arama olmasın diye), ama şeritlerin içindeki gerçek yükseklik "
    "çubukları hiç çizilmez -- yükseklik test edilen şey olduğu için ekrandan okunamamalı, sadece "
    "dokunarak/hissederek karşılaştırılmalı. Dokunma algılama ve sinyal mantığını etkilemez.",
    "carrier_freq_hz": "Elektroadhezyon sinyalinin taşıyıcı frekansı. Bu bir tasarım parametresi değil, "
    "rig'in donanım özelliği -- README'deki donanım tablosunda '125 Hz carrier frequency' olarak "
    "belirtiliyor.",
    "voltage_peak": "Sinyal jeneratörünün tepe voltajı (Vpp, amplifikatör öncesi); README'deki '4V "
    "peak' rig özelliğiyle eşleşir. UYARI: 50x amplifikatörle çarpılınca dokunma yüzeyinde ~100V'a "
    "çıkıyor -- yükseltmeden önce README'nin güvenlik notunu okuyun.",
    "ir_sample_hz_nominal": "IR çerçevenin nominal örnekleme hızı; README'de belirtilen Nexio "
    "NIB170BP donanımının spesifikasyonu (~100 Hz), bir tasarım tercihi değil. Yazılım tabanlı "
    "zamanlamanın (perf_counter) bu sınırlamayı nasıl aştığı README'nin 'Rendering Method' "
    "bölümünde anlatılıyor.",
    "rng_seed": "Deneme sırasını karıştıran rastgele sayı üreteci tohumu. Boş bırakılırsa rastgele "
    "bir tohum seçilir; gerçekleşen tohum yine de tekrarlanabilirlik için config snapshot'ına "
    "kaydedilir.",
    "staircase_dh_start_pct": "Sadece staircase_pilot modunda kullanılır: adaptif staircase'in "
    "başlangıç adım büyüklüğü. Genel 1-yukarı/2-aşağı staircase pratiği (Levitt, 1971 tarzı "
    "tasarımların ortak kuralı) -- bu depoya özgü bir referansa bağlı değil.",
    "staircase_dh_min_pct": "Sadece staircase_pilot modunda kullanılır: adaptif adımın "
    "küçülebileceği minimum büyüklük.",
    "staircase_dh_step_pct": "Sadece staircase_pilot modunda kullanılır: her ters dönüşte adımın "
    "ne kadar küçültüleceği.",
    "staircase_n_reversals": "Sadece staircase_pilot modunda kullanılır: durmadan önce beklenecek "
    "toplam ters dönüş sayısı.",
    "staircase_n_reversals_averaged": "Sadece staircase_pilot modunda kullanılır: eşik hesabında "
    "ortalamaya dahil edilecek son ters dönüş sayısı.",
}


def _load_initial_config() -> ExperimentConfig:
    if LAST_USED_PATH.exists():
        try:
            return load_experiment_config(LAST_USED_PATH)
        except Exception:
            pass
    return load_experiment_config(DEFAULT_CONFIG_PATH)


class LauncherApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Deney Kontrol Paneli")
        self.root.geometry("760x820")
        self.root.minsize(560, 420)

        # Deliberately left on each platform's native ttk theme (aqua on macOS,
        # vista/winnative on Windows) rather than forcing "clam": on the old
        # Tcl/Tk 8.5 that macOS and some Windows Python installs still ship,
        # forcing a non-native theme has been observed to render ttk widgets
        # fully invisible instead of raising an error.
        style = ttk.Style()
        style.configure("Apply.TButton", font=("TkDefaultFont", 11, "bold"), padding=8)
        style.configure("Header.TLabel", font=("TkDefaultFont", 14, "bold"))
        style.configure("Status.TLabel", foreground="#666666")
        style.configure("Help.TLabel", foreground="#777777", font=("TkDefaultFont", 9))

        self.vars: dict[str, tk.Variable] = {}
        self.process: subprocess.Popen | None = None
        self._plot_image: ImageTk.PhotoImage | None = None
        self._launch_started_at = 0.0
        self._launch_cfg: ExperimentConfig | None = None
        self._launch_dry_run = False
        self._tab_canvases: dict[str, tk.Canvas] = {}
        self._current_canvas: tk.Canvas | None = None

        root.rowconfigure(1, weight=1)
        root.columnconfigure(0, weight=1)

        ttk.Label(root, text="Taktil Çubuk Yükseklik Ayrımı Deneyi", style="Header.TLabel").grid(
            row=0, column=0, sticky="w", padx=16, pady=(16, 4)
        )

        notebook = ttk.Notebook(root)
        notebook.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))

        for group_title, group_fields in FIELD_GROUPS:
            tab_content = self._build_scrollable_tab(notebook, group_title)
            for i, (attr, label, kind) in enumerate(group_fields):
                self._build_field(tab_content, i, attr, label, kind)

        notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)
        if notebook.tabs():
            self._current_canvas = self._tab_canvases.get(notebook.tabs()[0])

        bottom = ttk.Frame(root, padding=(16, 0, 16, 16))
        bottom.grid(row=2, column=0, sticky="ew")

        run_frame = ttk.LabelFrame(bottom, text="Çalıştırma Seçenekleri", padding=10)
        run_frame.pack(fill="x", pady=(0, 6))
        self.windowed_var = tk.BooleanVar(value=False)
        self.dry_run_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(run_frame, text="Pencereli çalıştır (tam ekran yerine)", variable=self.windowed_var).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Checkbutton(
            run_frame, text="Dry-run (donanım/pygame yok, sadece uyum kontrolü)", variable=self.dry_run_var
        ).grid(row=1, column=0, sticky="w")

        self.status_var = tk.StringVar(value="")
        ttk.Label(bottom, textvariable=self.status_var, style="Status.TLabel").pack(fill="x", pady=(0, 2))

        self.hardware_status_var = tk.StringVar(value="")
        ttk.Label(bottom, textvariable=self.hardware_status_var, style="Status.TLabel").pack(fill="x", pady=(0, 6))

        console_frame = ttk.LabelFrame(bottom, text="Konsol Çıktısı (son oturum)", padding=6)
        console_frame.pack(fill="x", pady=(0, 6))
        self.console_text = tk.Text(
            console_frame, height=6, wrap="word", font=("TkFixedFont", 9), state="disabled"
        )
        console_scroll = ttk.Scrollbar(console_frame, orient="vertical", command=self.console_text.yview)
        self.console_text.configure(yscrollcommand=console_scroll.set)
        self.console_text.pack(side="left", fill="both", expand=True)
        console_scroll.pack(side="right", fill="y")

        plot_frame = ttk.LabelFrame(bottom, text="Son Oturum: Psychometric Eğri", padding=10)
        plot_frame.pack(fill="x", pady=(0, 6))
        self.plot_label = ttk.Label(
            plot_frame, text="Henüz bir oturum çalıştırılmadı.", anchor="center", justify="center"
        )
        self.plot_label.pack(fill="both", expand=True)

        button_row = ttk.Frame(bottom)
        button_row.pack(fill="x")
        ttk.Button(button_row, text="Varsayılana Sıfırla", command=self._reset_to_default).pack(side="left")
        self.apply_button = ttk.Button(button_row, text="Apply", style="Apply.TButton", command=self._on_apply)
        self.apply_button.pack(side="right")

        self._populate(_load_initial_config())

    def _build_scrollable_tab(self, notebook: ttk.Notebook, title: str) -> ttk.Frame:
        outer = ttk.Frame(notebook)
        notebook.add(outer, text=title)
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        canvas = tk.Canvas(outer, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        content = ttk.Frame(canvas, padding=12)
        content_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def _on_content_configure(_event: object) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event: tk.Event) -> None:
            canvas.itemconfig(content_id, width=event.width)

        content.bind("<Configure>", _on_content_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        self._tab_canvases[str(outer)] = canvas
        return content

    def _on_tab_changed(self, event: tk.Event) -> None:
        notebook = event.widget
        self._current_canvas = self._tab_canvases.get(notebook.select())

    def _on_mousewheel(self, event: tk.Event) -> None:
        canvas = self._current_canvas
        if canvas is None:
            return
        delta = event.delta if sys.platform == "darwin" else int(event.delta / 120)
        canvas.yview_scroll(int(-delta), "units")

    def _build_field(self, parent: ttk.Frame, i: int, attr: str, label: str, kind: str) -> None:
        row = i * 2
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=(6, 0))
        if kind == "bool":
            var = tk.BooleanVar()
            ttk.Checkbutton(parent, variable=var).grid(row=row, column=1, sticky="w", pady=(6, 0))
        elif kind == "mode":
            var = tk.StringVar()
            ttk.Combobox(parent, textvariable=var, values=MODE_CHOICES, state="readonly", width=22).grid(
                row=row, column=1, sticky="w", pady=(6, 0)
            )
        else:
            var = tk.StringVar()
            ttk.Entry(parent, textvariable=var, width=24).grid(row=row, column=1, sticky="w", pady=(6, 0))
        self.vars[attr] = var

        help_text = FIELD_HELP.get(attr)
        if help_text:
            ttk.Label(parent, text=help_text, style="Help.TLabel", wraplength=520, justify="left").grid(
                row=row + 1, column=0, columnspan=2, sticky="w", pady=(0, 6)
            )

    def _populate(self, cfg: ExperimentConfig) -> None:
        data = config_to_dict(cfg)
        for attr, var in self.vars.items():
            value = data.get(attr)
            if isinstance(var, tk.BooleanVar):
                var.set(bool(value))
            else:
                var.set("" if value is None else str(value))

    def _reset_to_default(self) -> None:
        self._populate(load_experiment_config(DEFAULT_CONFIG_PATH))
        self.status_var.set("Varsayılan config yüklendi.")

    def _collect_config(self) -> ExperimentConfig:
        kind_by_attr = {attr: kind for _, group in FIELD_GROUPS for attr, _, kind in group}
        kwargs: dict[str, Any] = {}
        for attr, var in self.vars.items():
            kind = kind_by_attr[attr]
            raw = var.get()
            if kind == "bool":
                kwargs[attr] = bool(raw)
            elif kind in ("str", "mode"):
                kwargs[attr] = str(raw).strip()
            elif kind == "optional_int":
                text = str(raw).strip()
                kwargs[attr] = int(text) if text else None
            elif kind == "int":
                kwargs[attr] = int(str(raw).strip())
            elif kind == "float":
                kwargs[attr] = float(str(raw).strip())
        return ExperimentConfig(**kwargs)

    def _on_apply(self) -> None:
        try:
            cfg = self._collect_config()
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Geçersiz konfigürasyon", str(exc))
            return
        if not cfg.participant_id:
            messagebox.showerror("Eksik alan", "Katılımcı ID boş olamaz.")
            return

        LAST_USED_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAST_USED_PATH.write_text(yaml.safe_dump(config_to_dict(cfg), sort_keys=False))

        dry_run = self.dry_run_var.get()
        cmd = [
            sys.executable, "-m", "experiment.main",
            "--config", str(LAST_USED_PATH),
            "--participant", cfg.participant_id,
        ]
        if self.windowed_var.get():
            cmd.append("--windowed")
        if dry_run:
            cmd.append("--dry-run")

        try:
            self.process = subprocess.Popen(cmd, cwd=REPO_ROOT)
        except OSError as exc:
            messagebox.showerror("Başlatılamadı", str(exc))
            return

        self._launch_started_at = time.time()
        self._launch_cfg = cfg
        self._launch_dry_run = dry_run

        self.apply_button.state(["disabled"])
        self.status_var.set(f"Çalışıyor: {cfg.participant_id} ({cfg.mode})...")
        self._plot_image = None
        self.plot_label.configure(image="", text="Oturum çalışıyor...")
        self.root.withdraw()
        threading.Thread(target=self._wait_for_process, daemon=True).start()

    def _wait_for_process(self) -> None:
        assert self.process is not None
        returncode = self.process.wait()
        self.root.after(0, self._on_process_done, returncode)

    def _on_process_done(self, returncode: int) -> None:
        self.process = None
        self.apply_button.state(["!disabled"])
        self.status_var.set(
            "Son oturum tamamlandı." if returncode == 0 else f"Son oturum hata ile bitti (kod {returncode})."
        )
        self.root.deiconify()
        self.root.lift()
        self._show_latest_plot()

    def _newest_since_launch(self, paths: Iterable[Path]) -> Path | None:
        candidates = [p for p in paths if p.stat().st_mtime >= self._launch_started_at - 1]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_mtime)

    def _show_latest_plot(self) -> None:
        cfg = self._launch_cfg
        if cfg is None:
            return
        try:
            if self._launch_dry_run:
                png_path = self._newest_since_launch(DATA_DIR.glob("dry_run_*.png"))
                if png_path is None:
                    self.plot_label.configure(text="Dry-run grafiği bulunamadı.", image="")
                    return
            elif cfg.mode == "staircase_pilot":
                self.plot_label.configure(
                    image="",
                    text="Pilot (staircase) modda çizilecek bir psychometric eğri yok; "
                    "eşik değeri thresholds.csv'ye yazıldı.",
                )
                return
            else:
                csv_path = self._newest_since_launch(DATA_DIR.glob(f"{cfg.participant_id}_*_trials.csv"))
                if csv_path is None:
                    self.plot_label.configure(
                        text="Bu oturum için deneme verisi bulunamadı (erken çıkılmış olabilir).", image=""
                    )
                    return
                from analysis.fit_psychometric import fit_psychometric, load_session_csvs, plot_psychometric

                levels, n_trials, n_taller = load_session_csvs([csv_path])
                if not levels:
                    self.plot_label.configure(
                        text="Kaydedilen deneme yok (pratik denemeler hariç tutulur).", image=""
                    )
                    return
                fit = fit_psychometric(levels, n_trials, n_taller)
                png_path = csv_path.with_name(csv_path.stem.replace("_trials", "") + "_fit.png")
                plot_psychometric(fit, png_path)
        except Exception as exc:  # noqa: BLE001 -- surfaced in the panel, not fatal to the GUI
            self.plot_label.configure(text=f"Eğri çizilemedi: {exc}", image="")
            return

        image = Image.open(png_path)
        max_width = 620
        if image.width > max_width:
            ratio = max_width / image.width
            image = image.resize((max_width, round(image.height * ratio)))
        self._plot_image = ImageTk.PhotoImage(image)
        self.plot_label.configure(image=self._plot_image, text="")


def main() -> None:
    root = tk.Tk()
    LauncherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
