import sqlite3
import os
import datetime
import uuid
import traceback
import base64
import hashlib
import json
import secrets
from kivymd.app import MDApp
from kivy.lang import Builder
from kivy.utils import get_color_from_hex
from kivy.core.text import LabelBase
from kivy.properties import NumericProperty, StringProperty, ListProperty
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivy.uix.boxlayout import BoxLayout
from kivymd.toast import toast
from kivymd.uix.card import MDCard
from kivymd.uix.boxlayout import MDBoxLayout
from kivy.metrics import dp
from kivy.uix.spinner import Spinner
from kivy.clock import Clock
from kivymd.uix.textfield import MDTextField
from kivymd.uix.label import MDLabel, MDIcon
from kivy.core.clipboard import Clipboard
from kivy.base import ExceptionHandler, ExceptionManager
import arabic_reshaper
from bidi.algorithm import get_display

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF
from xml.sax.saxutils import escape as xml_escape
import re
import unicodedata

from kivy.utils import platform as _kivy_platform
IS_ANDROID = (_kivy_platform == "android")

# =====================================================================
#  ثوابت
# =====================================================================
def _find_font():
    for d in (os.path.dirname(os.path.abspath(__file__)), os.getcwd()):
        try:
            for fn in os.listdir(d):
                if fn.lower() == "sahel.ttf":
                    return os.path.join(d, fn)
        except Exception:
            pass
    return "sahel.ttf"


FONT_FILE = _find_font()
LOGO_FILE = "logo.png"
APP_VERSION = "1.1.1"

FREE_LIMIT_CARS = 3
FREE_LIMIT_CLIENTS = 3
FREE_LIMIT_CONTRACTS = 3
FREE_PRICE_DZD = 15000

PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA6y9ERz0qRyiOeMa3vpwJ
fnqfKFGqy5fGj5ordJjU6m39nMEeqV5u6sj+wEpYxDVT64TArJBowh94EuauEIQB
M7vHWdGpXieTRK+uCtUoOra5LVWdhL+br97PGLlB9ELJNbtCV2+8hSe9u66zUGii
OgGfJEe7AlN1PqMVf1sOBBSTHdtamqlThbwno7FyvPNOseDeHTQ4mmU4fR/aSz3O
Tc3kD8L7roiji2C9Zomh5xrgiUSasCpe/rV65eYiEuutcGbRhFksl1Dm1GZwdPuI
3mX/q/bmJfdDdMgzEk29Tv9h7TWUgNHLljoIKMOe7odfvdbC98JR9BnLqY2n8amQ
9QIDAQAB
-----END PUBLIC KEY-----
"""

RECOVERY_SECRET = "SamirPythDZ_recovery_2025_v1"

# ---- fix: adaptive_height must also apply the initial height (KivyMD 1.1.1 + Android) ----
try:
    from kivymd.uix import MDAdaptiveWidget as _MDAW
    from kivy.uix.label import Label as _KLabel
    from kivy.uix.floatlayout import FloatLayout as _KFloat
    from kivy.uix.screenmanager import Screen as _KScreen
    from kivy.clock import Clock as _KClock

    def _on_adaptive_height(self, md_widget, value):
        if not value:
            return
        self.size_hint_y = None
        if isinstance(self, _KLabel):
            self.bind(texture_size=lambda *a: setattr(self, "height", self.texture_size[1]))
        elif not isinstance(self, (_KFloat, _KScreen)):
            self.bind(minimum_height=self.setter("height"))

            def _apply(dt, w=self):
                try:
                    w.height = w.minimum_height
                except Exception:
                    pass
            _KClock.schedule_once(_apply, 0)
            _KClock.schedule_once(_apply, 0.3)

    _MDAW.on_adaptive_height = _on_adaptive_height

    if not issubclass(MDCard, _MDAW):
        _OrigMDCard = MDCard

        class MDCard(_MDAW, _OrigMDCard):
            pass

        from kivy.factory import Factory as _KFactory
        _KFactory.unregister("MDCard")
        _KFactory.register("MDCard", cls=MDCard)
except Exception as _e:
    print("adaptive patch error:", _e)

if os.path.exists(FONT_FILE):
    try:
        for font_name in ["Roboto", "RobotoThin", "RobotoLight", "RobotoMedium", "RobotoBlack", "Roboto-Regular", "Roboto-Medium", "Roboto-Bold", "Roboto-Light"]:
            LabelBase.register(
                name=font_name,
                fn_regular=FONT_FILE,
                fn_bold=FONT_FILE,
                fn_italic=FONT_FILE,
                fn_bolditalic=FONT_FILE
            )
    except Exception:
        pass


# =====================================================================
#  دوال مساعدة
# =====================================================================
def is_arabic(text):
    try:
        return any(('\u0600' <= ch <= '\u06FF') or ('\u0750' <= ch <= '\u077F')
                   or ('\uFB50' <= ch <= '\uFDFF') or ('\uFE70' <= ch <= '\uFEFF')
                   for ch in str(text))
    except Exception:
        return False


def ar(text):
    if not text:
        return ""
    s = clean_text(text)
    if not is_arabic(s):
        return s
    try:
        out = []
        for line in s.split('\n'):
            if not line:
                out.append('')
                continue
            if not is_arabic(line):
                out.append(line)
                continue
            try:
                shaped = arabic_reshaper.reshape(line)
                out.append(get_display(shaped, base_dir='R'))
            except Exception:
                out.append(line)
        return '\n'.join(out)
    except Exception:
        return s


_MARKUP_RE = re.compile(r'(\[[^\]]+\])')


def ar_markup(text):
    if not text:
        return ""
    s = clean_text(text)
    if not is_arabic(s):
        return s
    try:
        final_lines = []
        for line in s.split('\n'):
            parts = _MARKUP_RE.split(line)
            rebuilt = []
            for part in parts:
                if not part:
                    continue
                if _MARKUP_RE.fullmatch(part):
                    rebuilt.append(part)
                else:
                    rebuilt.append(ar(part))
            final_lines.append(''.join(rebuilt))
        return '\n'.join(final_lines)
    except Exception:
        return s


def ar_lines(text, max_chars=40):
    if not text:
        return ""
    s = clean_text(text)
    out = []
    for para in s.split("\n"):
        if not is_arabic(para):
            out.append(para)
            continue
        cur = ""
        for w in para.split(" "):
            trial = (cur + " " + w).strip()
            if len(trial) > max_chars and cur:
                out.append(ar(cur))
                cur = w
            else:
                cur = trial
        if cur:
            out.append(ar(cur))
    return "\n".join(out)


# =====================================================================
#  مسارات التخزين
# =====================================================================
_APP_ROOT = None


def app_storage_dir():
    if _kivy_platform == "android":
        cands = [
            "/storage/emulated/0/Documents/SamirPythDZ",
            "/storage/emulated/0/SamirPythDZ",
            "/sdcard/Documents/SamirPythDZ",
        ]
    else:
        cands = [
            os.path.join(os.path.expanduser("~"), "Documents", "SamirPythDZ"),
            os.path.join(os.path.expanduser("~"), "SamirPythDZ"),
        ]
    for d in cands:
        try:
            os.makedirs(d, exist_ok=True)
            t = os.path.join(d, ".wt")
            open(t, "w").close()
            os.remove(t)
            return d
        except Exception:
            continue
    if _kivy_platform == "android":
        try:
            from jnius import autoclass
            _act = autoclass('org.kivy.android.PythonActivity').mActivity
            _ext = _act.getExternalFilesDir(None)
            if _ext is not None:
                d = os.path.join(_ext.getAbsolutePath(), "SamirPythDZ")
                os.makedirs(d, exist_ok=True)
                return d
        except Exception:
            pass
        try:
            from android.storage import app_storage_path
            d = os.path.join(app_storage_path(), "SamirPythDZ")
            os.makedirs(d, exist_ok=True)
            return d
        except Exception:
            pass
    d = os.path.join(os.getcwd(), "SamirPythDZ")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        return os.getcwd()
    return d


def request_android_permissions():
    if not IS_ANDROID:
        return
    try:
        from android.permissions import request_permissions
        request_permissions([
            "android.permission.READ_EXTERNAL_STORAGE",
            "android.permission.WRITE_EXTERNAL_STORAGE",
            "android.permission.READ_MEDIA_IMAGES",
        ])
    except Exception as e:
        print("permissions error:", e)


def app_root():
    global _APP_ROOT
    if _APP_ROOT is None:
        _APP_ROOT = app_storage_dir()
    return _APP_ROOT


def db_dir():
    d = os.path.join(app_root(), "database")
    try: os.makedirs(d, exist_ok=True)
    except Exception: pass
    return d


def csv_dir():
    d = os.path.join(app_root(), "csv")
    try: os.makedirs(d, exist_ok=True)
    except Exception: pass
    return d


def private_dir():
    if _kivy_platform == "android":
        base = None
        try:
            from jnius import autoclass
            _act = autoclass('org.kivy.android.PythonActivity').mActivity
            base = _act.getFilesDir().getAbsolutePath()
        except Exception:
            try:
                from android.storage import app_storage_path
                base = app_storage_path()
            except Exception:
                base = None
        if base:
            d = os.path.join(base, "SamirPythDZ")
            try:
                os.makedirs(d, exist_ok=True)
                return d
            except Exception:
                pass
    return app_root()


def get_db_path():
    dbd = os.path.join(private_dir(), "database")
    try:
        os.makedirs(dbd, exist_ok=True)
    except Exception:
        pass
    new_path = os.path.join(dbd, "dealership_v2.db")
    if not os.path.exists(new_path):
        import shutil
        for old_path in (os.path.join(db_dir(), "dealership_v2.db"),
                         "dealership_v2.db"):
            if os.path.exists(old_path) and os.path.abspath(old_path) != os.path.abspath(new_path):
                try:
                    shutil.copy2(old_path, new_path)
                    break
                except Exception:
                    pass
    return new_path


# =====================================================================
#  الأمان (PIN محصّن)
# =====================================================================
def _get_or_create_device_salt():
    try:
        conn = sqlite3.connect(get_db_path())
        row = conn.execute("SELECT value FROM settings WHERE key='pin_salt'").fetchone()
        if row and row[0]:
            conn.close()
            return row[0]
        new_salt = secrets.token_hex(16)
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('pin_salt', ?)", (new_salt,))
        conn.commit()
        conn.close()
        return new_salt
    except Exception:
        return "SamirPythDZ_fallback_salt"


def hash_pin(pin: str) -> str:
    salt = _get_or_create_device_salt()
    try:
        dk = hashlib.pbkdf2_hmac(
            'sha256',
            str(pin).encode('utf-8'),
            salt.encode('utf-8'),
            5000
        )
        return dk.hex()
    except Exception:
        return hashlib.sha256((salt + str(pin)).encode("utf-8")).hexdigest()


def get_pin_hash():
    try:
        conn = sqlite3.connect(get_db_path())
        row = conn.execute("SELECT value FROM settings WHERE key='security_pin'").fetchone()
        conn.close()
        return row[0] if row and row[0] else ""
    except Exception:
        return ""


def set_pin_hash(pin: str):
    try:
        conn = sqlite3.connect(get_db_path())
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('security_pin', ?)",
                     (hash_pin(pin),))
        conn.execute("DELETE FROM settings WHERE key IN ('pin_fail_count', 'pin_lock_until')")
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def clear_pin():
    try:
        conn = sqlite3.connect(get_db_path())
        conn.execute("DELETE FROM settings WHERE key='security_pin'")
        conn.execute("DELETE FROM settings WHERE key IN ('pin_fail_count', 'pin_lock_until')")
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_fail_count():
    try:
        conn = sqlite3.connect(get_db_path())
        row = conn.execute("SELECT value FROM settings WHERE key='pin_fail_count'").fetchone()
        conn.close()
        return int(row[0]) if row and row[0] else 0
    except Exception:
        return 0


def get_lock_until():
    try:
        conn = sqlite3.connect(get_db_path())
        row = conn.execute("SELECT value FROM settings WHERE key='pin_lock_until'").fetchone()
        conn.close()
        if not row or not row[0]:
            return 0
        until = datetime.datetime.fromisoformat(row[0])
        remaining = (until - datetime.datetime.now()).total_seconds()
        return max(0, int(remaining))
    except Exception:
        return 0


def register_fail():
    try:
        fails = get_fail_count() + 1
        lock_seconds = 0
        if fails >= 5:
            lock_seconds = 30
        if fails >= 7:
            lock_seconds = 120
        if fails >= 10:
            lock_seconds = 600
        conn = sqlite3.connect(get_db_path())
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('pin_fail_count', ?)",
                     (str(fails),))
        if lock_seconds > 0:
            until = (datetime.datetime.now() +
                     datetime.timedelta(seconds=lock_seconds)).isoformat()
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('pin_lock_until', ?)",
                         (until,))
        conn.commit()
        conn.close()
        return lock_seconds
    except Exception:
        return 0


def reset_fail_counter():
    try:
        conn = sqlite3.connect(get_db_path())
        conn.execute("DELETE FROM settings WHERE key IN ('pin_fail_count', 'pin_lock_until')")
        conn.commit()
        conn.close()
    except Exception:
        pass


def generate_recovery_code(device_id):
    if not device_id:
        return ""
    h = hashlib.sha256(
        (device_id.strip().upper() + "|" + RECOVERY_SECRET).encode("utf-8")
    ).hexdigest()
    return h[:8].upper()


def check_recovery_code(device_id, entered):
    if not entered:
        return False
    return entered.strip().upper() == generate_recovery_code(device_id)


# =====================================================================
#  بنود العقد الافتراضية
# =====================================================================
DEFAULT_ARTICLES = {
    "ar": [
        {"title": "المادة 01: طرفي العقد",
         "body": "الطرف الأول: {company}.\nالطرف الثاني (الزبون): {name}، الهوية: {nid}\nالميلاد: {birth}، العنوان: {address}"},
        {"title": "المادة 02: موضوع العقد",
         "body": "تم الاتفاق بين الطرفين أن يقوم الطرف الأول بدور الوسيط التجاري لإتمام عملية بيع السيارة نوع: {car}، المسافة: {km} كلم.\nالنسخة: {trim}، اللون: {color}، علبة السرعة: {gearbox}.\nرقم التسجيل: {plate}، رقم الهيكل: {chassis}."},
        {"title": "المادة 03: الشروط المالية",
         "body": "السعر الإجمالي المتفق عليه للسيارة هو: {price}. يلتزم الزبون بدفع المبلغ وفق الترتيبات المتفق عليها."},
        {"title": "المادة 04: الالتزامات",
         "body": "يقر الطرف الثاني بمعاينته للسيارة المعاينة التامة، ويتحمل المسؤولية الكاملة ابتداءً من تاريخ تسليم المفتاح ووثائق المركبة."},
        {"title": "المادة 05: الخاتمة",
         "body": "حرر هذا العقد ب{city} {when}، بحسن نية وباتفاق الطرفين في نسختين أصليتين لكل طرف نسخة للعمل بها عند الحاجة."},
    ],
    "fr": [
        {"title": "Article 01 : Parties",
         "body": "Première partie : {company}.\nDeuxième partie (le client) : {name}, piece d'identite N° : {nid}\nNe(e) le / a : {birth}, adresse : {address}"},
        {"title": "Article 02 : Objet",
         "body": "Il est convenu que la premiere partie agit en qualite d'intermediaire commercial pour la vente du vehicule : {car}, kilometrage : {km} km.\nVersion : {trim}, couleur : {color}, Boite : {gearbox}.\nN° d'immatriculation : {plate}, N° de Chassis : {chassis}."},
        {"title": "Article 03 : Conditions financieres",
         "body": "Le prix total convenu est de : {price}. Le client s'engage a regler ce montant selon les modalites convenues."},
        {"title": "Article 04 : Obligations",
         "body": "La deuxieme partie reconnait avoir examine le vehicule et en assume l'entiere responsabilite a compter de la remise des cles et des documents."},
        {"title": "Article 05 : Cloture",
         "body": "Fait a {city} {when}. En deux exemplaires originaux, un pour chaque partie."},
    ],
}


def get_contract_articles(lang="ar"):
    try:
        conn = sqlite3.connect(get_db_path())
        row = conn.execute("SELECT value FROM settings WHERE key=?",
                           (f"contract_articles_{lang}",)).fetchone()
        conn.close()
        if row and row[0]:
            data = json.loads(row[0])
            if isinstance(data, list) and len(data) > 0:
                return data
    except Exception:
        pass
    return DEFAULT_ARTICLES[lang]


def save_contract_articles(lang, articles):
    try:
        conn = sqlite3.connect(get_db_path())
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                     (f"contract_articles_{lang}", json.dumps(articles, ensure_ascii=False)))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


# =====================================================================
#  الترجمة
# =====================================================================
TRANSLATIONS = {
    "ar": {
        "app_title": "Showroom Manager",
        "tab_cars": "السيارات", "tab_clients": "الزبائن",
        "tab_contracts": "العقود", "tab_settings": "الإعدادات",
        "stat_available": "متوفر", "stat_reserved": "محجوز", "stat_sold": "مباع",
        "add_car_title": "إضافة سيارة جديدة", "edit_car_title": "تعديل بيانات السيارة",
        "car_name_hint": "اسم السيارة (مثال: Peugeot 2008)",
        "car_name_fr_hint": "اسم السيارة بالفرنسية",
        "client_name_fr_hint": "الاسم واللقب بالفرنسية",
        "mileage_hint": "المسافة المقطوعة (كلم)",
        "price_hint": "السعر (مثال: 350 مليون)",
        "trim_hint": "النسخة (Version)", "color_hint": "اللون",
        "plate_hint": "رقم التسجيل", "chassis_hint": "رقم الهيكل (VIN)",
        "profit_margin_hint": "هامش الربح (مثال: 30 مليون)",
        "gearbox_label": "علبة السرعة:", "status_label": "الحالة:",
        "not_specified": "غير محدد", "automatic": "أوتوماتيك",
        "manual": "يدوي", "available": "متوفر", "reserved": "محجوز", "sold": "مباع",
        "add_client_title": "إضافة زبون جديد",
        "edit_client_title": "تعديل بيانات الزبون",
        "client_name_hint": "الاسم واللقب",
        "nid_hint": "رقم التعريف الوطني (NIN)",
        "birth_hint": "تاريخ ومكان الميلاد",
        "address_hint": "العنوان", "address_fr_hint": "العنوان بالفرنسية",
        "add_contract_title": "تسجيل عقد وساطة جديد",
        "edit_contract_title": "تعديل العقد",
        "car_label": "السيارة", "client_label": "الزبون",
        "select_car": "اختر سيارة", "select_client": "اختر زبوناً",
        "no_cars_avail": "لا توجد سيارات متوفرة",
        "no_clients_avail": "لا توجد زبائن",
        "final_price_hint": "السعر الإجمالي النهائي",
        "paid_hint": "المبلغ المدفوع (العربون بالملايين)",
        "remaining_hint": "المبلغ المتبقي",
        "cancel": "إلغاء", "save": "حفظ", "save_changes": "حفظ التعديلات",
        "save_pdf": "حفظ وإنشاء PDF",
        "bank_section": "معلومات البنك", "bank_holder": "اسم صاحب الحساب",
        "bank_name": "اسم البنك", "bank_agency": "الوكالة",
        "bank_account": "رقم الحساب (RIB)",
        "db_section": "قاعدة البيانات",
        "backup_db": "حفظ نسخة احتياطية", "restore_db": "استرداد نسخة احتياطية",
        "lang_section": "لغة التطبيق / Langue", "lang_label": "",
        "car_options": "خيارات السيارة", "client_options": "خيارات الزبون",
        "contract_options": "خيارات العقد", "reserve_contract": "حجز / عقد جديد",
        "edit": "تعديل", "delete": "حذف", "close": "إغلاق",
        "edit_contract": "تعديل العقد", "order_receipt": "وصل طلب",
        "payment_order": "أمر بالدفع", "download_pdf": "تحميل PDF",
        "cancel_contract": "إلغاء العقد",
        "amount_to_pay_hint": "المبلغ المراد دفعه",
        "gen_pdf": "توليد PDF", "client_id_num": "رقم التعريف: ",
        "no_id": "بدون رقم تعريف", "price_label": "السعر: ",
        "remaining_label": "  |  المتبقي: ", "million": "مليون",
        "version_prefix": "النسخة: ", "color_prefix": "اللون: ",
        "gearbox_prefix": "العلبة: ", "plate_prefix": "التسجيل: ",
        "chassis_prefix": "الهيكل: ", "km_unit": "كلم",
        "lang_changed": "تم تغيير لغة التطبيق بنجاح",
        "saved_car_success": "تم إضافة السيارة بنجاح",
        "updated_car_success": "تم تعديل السيارة بنجاح",
        "saved_client_success": "تم إضافة زبون جديد بنجاح",
        "updated_client_success": "تم تعديل بيانات الزبون بنجاح",
        "car_sold_err": "هذه السيارة مباعة",
        "fill_car_price_err": "الرجاء إدخال اسم السيارة والسعر!",
        "fill_client_err": "الرجاء إدخال اسم الزبون على الأقل!",
        "fill_contract_err": "الرجاء اختيار السيارة والزبون وتحديد السعر!",
        "contract_pdf_success": "تم حفظ العقد وتوليد ملف PDF بنجاح",
        "bank_saved_success": "تم حفظ المعلومات بنجاح",
        "db_backup_success": "تم حفظ النسخة الاحتياطية: ",
        "db_restore_success": "تم استرداد قاعدة البيانات بنجاح",
        "car_deleted": "تم حذف السيارة", "client_deleted": "تم حذف الزبون",
        "cancel_contract_title": "محضر إلغاء عقد بالتراضي",
        "cancel_refund_hint": "المبلغ المرجّع للزبون",
        "confirm_cancel": "تأكيد الإلغاء وإنشاء PDF",
        "cancel_pdf_success": "تم إلغاء العقد وإنشاء محضر الإلغاء بالتراضي",
        "cancel_refund_needed": "الرجاء إدخال المبلغ المرجّع",
        "save_error": "حدث خطأ أثناء الحفظ!",
        "save_client_error": "حدث خطأ أثناء حفظ الزبون!",
        "data_id_error": "خطأ في تحديد البيانات!",
        "pick_id_file": "اختر ملف بطاقة التعريف أو جواز السفر",
        "order_pdf_success": "تم إنشاء وصل الطلب وحفظه",
        "pay_pdf_success": "تم إنشاء أمر بالدفع وحفظه",
        "enter_bank_first": "أدخل معلومات البنك أولاً",
        "enter_amount": "الرجاء إدخال المبلغ",
        "pdf_regenerated": "تم إعادة توليد ملف PDF",
        "confirm_restore_msg": "سيتم استبدال كل البيانات الحالية. متابعة؟",
        "invalid_backup": "الملف ليس نسخة صالحة",
        "pypdf_missing": "أضف pypdf لدمج PDF",
        "pick_backup_file": "اختر ملف النسخة الاحتياطية (.db)",
        "search_cars_hint": "ابحث بالاسم، التسجيل...",
        "search_clients_hint": "ابحث بالاسم أو NIN...",
        "search_contracts_hint": "ابحث بالاسم، السيارة...",
        "stat_dashboard": "لوحة الإحصائيات",
        "about_title": "حول التطبيق",
        "client_history": "سجل الزبون",
        "paste": "لصق",
        "enter_activation": "الرجاء إدخال الكود",
        "activation_bad": "الكود غير صحيح",
        "profit_section": "الأرباح",
        "profit_current": "الربح المحقق", "profit_expected": "الربح المتوقع",
        "profit_total": "الربح الكلي",
        "cars_section": "السيارات", "cars_available": "متوفرة",
        "cars_reserved": "محجوزة", "cars_sold": "مباعة",
        "contracts_section": "العقود والزبائن",
        "total_contracts": "إجمالي العقود",
        "month_contracts": "عقود هذا الشهر",
        "total_clients": "إجمالي الزبائن",
        "top_section": "الأوائل", "best_client": "أفضل زبون",
        "best_car": "أكثر سيارة مبيعاً", "contract_n": "عقد",
        "company_section": "معلومات الشركة",
        "company_logo": "شعار الشركة", "pick_logo": "اختيار",
        "company_name": "اسم الشركة", "company_rc": "رقم السجل التجاري",
        "company_nif": "رقم التعريف الجبائي (NIF)",
        "company_phone": "رقم الهاتف",
        "company_address": "العنوان (بالعربية)",
        "company_address_fr": "العنوان (بالفرنسية)",
        "company_city": "المدينة", "company_color": "لون مستندات PDF",
        "bank_edit": "تعديل معلومات البنك",
        "company_edit": "تعديل معلومات الشركة",
        "color_blue": "أزرق", "color_green": "أخضر", "color_red": "أحمر",
        "color_purple": "بنفسجي", "color_teal": "فيروزي",
        "color_maroon": "عنابي", "color_gold": "ذهبي",
        "color_black": "أسود", "color_navy_dark": "كحلي فاخر",
        "color_white": "أبيض",
        "upgrade_now": "ترقية الآن", "upgrade_title": "ترقية للنسخة الكاملة",
        "welcome_title": "مرحباً بك في Showroom Manager",
        "export_data": "تصدير البيانات",
        "export_cars": "تصدير السيارات (CSV)",
        "export_clients": "تصدير الزبائن (CSV)",
        "export_contracts": "تصدير العقود (CSV)",
        "security_section": "الأمان",
        "articles_section": "بنود عقد السمسرة",
        "articles_hint": "يمكنك إضافة أو حذف أو تعديل مواد العقد",
        "backup_share": "مشاركة النسخة خارجياً",
        "backup_export": "حفظ نسخة خارجية",
        "backup_exported": "تم حفظ النسخة: ",
        "backup_share_title": "مشاركة النسخة عبر",
        "forgot_pin": "نسيت كلمة السر؟",
        "forgot_pin_title": "استعادة كلمة السر",
        "forgot_pin_msg": "أرسل معرّف الجهاز للمطوّر لتحصل على رمز الاسترجاع:",
        "recovery_code_hint": "أدخل رمز الاسترجاع:",
        "recovery_bad": "رمز الاسترجاع غير صحيح",
        "recovery_ok": "تم إلغاء كلمة السر — أعد تعيينها",
        "wrong_pin_n": "محاولة خاطئة. المتبقي: ",
        "locked_for": "الحساب مقفل مؤقتاً لمدة ",
        "seconds": "ثانية",
        "too_many_attempts": "محاولات كثيرة خاطئة",
        "saved_ok": "تم الحفظ",
        "copied_ok": "تم النسخ",
        "verify": "تحقق",
        "copy_id_short": "نسخ",
        "premium_locked": "هذه الميزة متاحة في النسخة الكاملة فقط",
    },
    "fr": {
        "app_title": "Showroom Manager",
        "tab_cars": "Vehicules", "tab_clients": "Clients",
        "tab_contracts": "Contrats", "tab_settings": "Parametres",
        "stat_available": "Disponible", "stat_reserved": "Reserve", "stat_sold": "Vendu",
        "add_car_title": "Ajouter un vehicule", "edit_car_title": "Modifier le vehicule",
        "car_name_hint": "Nom (ex: Peugeot 2008)",
        "car_name_fr_hint": "Nom en francais",
        "client_name_fr_hint": "Nom et prenom en francais",
        "mileage_hint": "Kilometrage (km)",
        "price_hint": "Prix (ex: 350 Millions)",
        "trim_hint": "Version", "color_hint": "Couleur",
        "plate_hint": "Immatriculation", "chassis_hint": "N° Chassis (VIN)",
        "profit_margin_hint": "Marge (ex: 30 Millions)",
        "gearbox_label": "Boite:", "status_label": "Statut:",
        "not_specified": "Non specifie", "automatic": "Automatique",
        "manual": "Manuelle", "available": "Disponible",
        "reserved": "Reserve", "sold": "Vendu",
        "add_client_title": "Ajouter un client",
        "edit_client_title": "Modifier le client",
        "client_name_hint": "Nom et prenom",
        "nid_hint": "NIN",
        "birth_hint": "Date et lieu de naissance",
        "address_hint": "Adresse", "address_fr_hint": "Adresse en francais",
        "add_contract_title": "Nouveau contrat",
        "edit_contract_title": "Modifier le contrat",
        "car_label": "Vehicule", "client_label": "Client",
        "select_car": "Choisir un vehicule",
        "select_client": "Choisir un client",
        "no_cars_avail": "Aucun vehicule disponible",
        "no_clients_avail": "Aucun client",
        "final_price_hint": "Prix total final",
        "paid_hint": "Montant paye",
        "remaining_hint": "Montant restant",
        "cancel": "Annuler", "save": "Enregistrer",
        "save_changes": "Enregistrer",
        "save_pdf": "Enregistrer & PDF",
        "bank_section": "Infos bancaires",
        "bank_holder": "Titulaire du compte",
        "bank_name": "Nom de la banque", "bank_agency": "Agence",
        "bank_account": "N° de compte (RIB)",
        "db_section": "Base de donnees",
        "backup_db": "Sauvegarder", "restore_db": "Restaurer",
        "lang_section": "Langue / اللغة", "lang_label": "",
        "car_options": "Options", "client_options": "Options",
        "contract_options": "Options", "reserve_contract": "Reservation",
        "edit": "Modifier", "delete": "Supprimer", "close": "Fermer",
        "edit_contract": "Modifier", "order_receipt": "Bon de commande",
        "payment_order": "Ordre de versement", "download_pdf": "PDF",
        "cancel_contract": "Annuler le contrat",
        "amount_to_pay_hint": "Montant a payer",
        "gen_pdf": "Generer PDF", "client_id_num": "NIN: ",
        "no_id": "Sans NIN", "price_label": "Prix: ",
        "remaining_label": "  |  Reste: ", "million": "Millions",
        "version_prefix": "Version: ", "color_prefix": "Couleur: ",
        "gearbox_prefix": "Boite: ", "plate_prefix": "Matricule: ",
        "chassis_prefix": "Chassis: ", "km_unit": "km",
        "lang_changed": "Langue changee",
        "saved_car_success": "Vehicule ajoute",
        "updated_car_success": "Vehicule modifie",
        "saved_client_success": "Client ajoute",
        "updated_client_success": "Client modifie",
        "car_sold_err": "Vendu", "fill_car_price_err": "Nom et prix requis!",
        "fill_client_err": "Nom du client requis!",
        "fill_contract_err": "Selectionnez vehicule, client et prix!",
        "contract_pdf_success": "Contrat et PDF generes",
        "bank_saved_success": "Enregistre",
        "db_backup_success": "Sauvegarde: ",
        "db_restore_success": "Restaure",
        "car_deleted": "Vehicule supprime", "client_deleted": "Client supprime",
        "cancel_contract_title": "PV de resiliation",
        "cancel_refund_hint": "Montant restitue",
        "confirm_cancel": "Confirmer & PDF",
        "cancel_pdf_success": "Contrat resilie",
        "cancel_refund_needed": "Saisir montant",
        "save_error": "Erreur enregistrement!",
        "save_client_error": "Erreur client!",
        "data_id_error": "Erreur identification!",
        "pick_id_file": "Choisir piece d'identite",
        "order_pdf_success": "Bon de commande cree",
        "pay_pdf_success": "Ordre de versement cree",
        "enter_bank_first": "Infos bancaires requises",
        "enter_amount": "Saisir montant",
        "pdf_regenerated": "PDF regenere",
        "confirm_restore_msg": "Remplacer toutes les donnees?",
        "invalid_backup": "Sauvegarde invalide",
        "pypdf_missing": "Ajouter pypdf",
        "pick_backup_file": "Choisir sauvegarde (.db)",
        "search_cars_hint": "Chercher...",
        "search_clients_hint": "Chercher...",
        "search_contracts_hint": "Chercher...",
        "stat_dashboard": "Tableau de bord",
        "about_title": "A propos",
        "client_history": "Historique",
        "paste": "Coller",
        "enter_activation": "Saisir le code",
        "activation_bad": "Code incorrect",
        "profit_section": "Benefices",
        "profit_current": "Realise", "profit_expected": "Attendu",
        "profit_total": "Total",
        "cars_section": "Vehicules", "cars_available": "Disponibles",
        "cars_reserved": "Reserves", "cars_sold": "Vendus",
        "contracts_section": "Contrats & Clients",
        "total_contracts": "Total contrats",
        "month_contracts": "Ce mois",
        "total_clients": "Total clients",
        "top_section": "Top", "best_client": "Meilleur client",
        "best_car": "Top vehicule", "contract_n": "contrats",
        "company_section": "Societe",
        "company_logo": "Logo", "pick_logo": "Choisir",
        "company_name": "Nom societe", "company_rc": "N° RC",
        "company_nif": "NIF",
        "company_phone": "Telephone",
        "company_address": "Adresse (ar)",
        "company_address_fr": "Adresse (fr)",
        "company_city": "Ville", "company_color": "Couleur PDF",
        "bank_edit": "Modifier banque",
        "company_edit": "Modifier societe",
        "color_blue": "Bleu", "color_green": "Vert", "color_red": "Rouge",
        "color_purple": "Violet", "color_teal": "Turquoise",
        "color_maroon": "Bordeaux", "color_gold": "Dore",
        "color_black": "Noir", "color_navy_dark": "Marine",
        "color_white": "Blanc",
        "upgrade_now": "Mettre a niveau",
        "upgrade_title": "Version complete",
        "welcome_title": "Bienvenue dans Showroom Manager",
        "export_data": "Exporter",
        "export_cars": "Exporter Vehicules (CSV)",
        "export_clients": "Exporter Clients (CSV)",
        "export_contracts": "Exporter Contrats (CSV)",
        "security_section": "Securite",
        "articles_section": "Articles du contrat",
        "articles_hint": "Ajouter, supprimer ou modifier les articles",
        "backup_share": "Partager la sauvegarde",
        "backup_export": "Exporter une copie",
        "backup_exported": "Sauvegarde enregistree: ",
        "backup_share_title": "Partager via",
        "forgot_pin": "Code oublie ?",
        "forgot_pin_title": "Recuperer le code",
        "forgot_pin_msg": "Envoyez l'ID de l'appareil au developpeur pour recevoir le code de recuperation :",
        "recovery_code_hint": "Entrez le code de recuperation :",
        "recovery_bad": "Code de recuperation incorrect",
        "recovery_ok": "Code supprime - redefinissez-le",
        "wrong_pin_n": "Tentatives restantes : ",
        "locked_for": "Verrouille pendant ",
        "seconds": "secondes",
        "too_many_attempts": "Trop de tentatives",
        "saved_ok": "Enregistre",
        "copied_ok": "Copie",
        "verify": "Verifier",
        "copy_id_short": "Copier",
        "premium_locked": "Cette fonctionnalite est reservee a la version complete",
    }
}


# =====================================================================
#  تنظيف النصوص
# =====================================================================
_CHAR_MAP = {
    "\u2019": "'", "\u2018": "'", "\u02bc": "'", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"',
    "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u2026": "...",
    "\u00a0": " ", "\u202f": " ", "\u2009": " ", "\u2007": " ",
    "\u200b": None, "\ufeff": None, "\u00ad": None, "\u2060": None,
}
_CHAR_TRANSLATE = {ord(k): v for k, v in _CHAR_MAP.items()}


def _fix_mojibake(s):
    if not any(m in s for m in ("Ã", "Â", "â€", "Ø", "Ù")):
        return s
    for enc in ("cp1252", "latin-1"):
        try:
            return s.encode(enc).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return s


def clean_text(text):
    if text is None:
        return ""
    s = _fix_mojibake(str(text))
    s = unicodedata.normalize("NFC", s)
    return s.translate(_CHAR_TRANSLATE)


# =====================================================================
#  ثيمات PDF
# =====================================================================
PDF_THEMES = {
    "blue":      {"navy": "#0B5394", "gold": "#F1C40F", "white_theme": False},
    "green":     {"navy": "#1E8449", "gold": "#F1C40F", "white_theme": False},
    "red":       {"navy": "#922B21", "gold": "#F1C40F", "white_theme": False},
    "purple":    {"navy": "#6C3483", "gold": "#F1C40F", "white_theme": False},
    "teal":      {"navy": "#0E6251", "gold": "#F1C40F", "white_theme": False},
    "maroon":    {"navy": "#78281F", "gold": "#F5B041", "white_theme": False},
    "gold":      {"navy": "#7D6608", "gold": "#F1C40F", "white_theme": False},
    "black":     {"navy": "#1C1C1C", "gold": "#7F8C8D", "white_theme": False},
    "navy_dark": {"navy": "#0B1F3A", "gold": "#D4AF37", "white_theme": False},
    "white":     {"navy": "#FFFFFF", "gold": "#0B5394", "white_theme": True},
}

NAVY = colors.HexColor("#0B5394")
GOLD = colors.HexColor("#F1C40F")
_current_theme_name = "blue"
WHITE_THEME_MODE = False


def apply_pdf_theme(theme_name):
    global NAVY, GOLD, _current_theme_name, WHITE_THEME_MODE
    if theme_name not in PDF_THEMES:
        theme_name = "blue"
    _current_theme_name = theme_name
    t = PDF_THEMES[theme_name]
    NAVY = colors.HexColor(t["navy"])
    GOLD = colors.HexColor(t["gold"])
    WHITE_THEME_MODE = t.get("white_theme", False)


GRID_C = colors.HexColor("#D5DBE3")
ZEBRA = colors.HexColor("#EEF3F9")
FALLBACK_FONT = "Helvetica"


# =====================================================================
#  ترجمة PDF
# =====================================================================
PDF_TR = {
    "ar": {
        "company": "شركة متجر السيارات - رمضان جمال",
        "tagline": "لبيع وشراء السيارات والخدمات التجارية",
        "footer": "العنوان: رمضان جمال، سكيكدة، الجزائر",
        "default_client": "زبون", "default_city": "سكيكدة",
        "contract_title": "عقد وساطة تجارية لشراء / بيع سيارة",
        "receipt_title": "إيصال دفع مالي ومعاملة بيع",
        "order_title": "وصل طلب سيارة", "pay_title": "أمر بالدفع",
        "f_contract": "عقد وساطة", "f_order": "وصل طلب", "f_pay": "أمر بالدفع",
        "contract_no": "رقم العقد", "date": "التاريخ", "time": "الوقت",
        "when_dt": "بتاريخ {d} على الساعة {t}", "when_d": "بتاريخ {d}",
        "sig_company": "إمضاء وخاتم المؤسسة", "sig_client": "إمضاء الزبون",
        "sig_cashier": "توقيع أمين الصندوق / المسير", "sig_client_ok": "توقيع المصادقة من الزبون",
        "sig_payer": "إمضاء الآمر بالدفع", "sig_bank": "ختم وإمضاء البنك",
        "t_client": "معلومات الزبون", "t_client_payer": "معلومات الزبون (الآمر بالدفع)",
        "t_car": "معلومات المركبة", "t_car_ordered": "معلومات السيارة المطلوبة",
        "t_car_pay": "معلومات السيارة",
        "t_bank": "معلومات البنك (المستفيد)", "t_amount": "المبلغ",
        "t_fin": "التفاصيل المالية", "h_amount": "المبلغ (دج)",
        "l_name": "الاسم الكامل", "l_nid": "رقم التعريف الوطني",
        "l_birth": "تاريخ ومكان الميلاد", "l_address": "العنوان",
        "l_model": "نوع السيارة", "l_trim": "النسخة", "l_color": "اللون",
        "l_gearbox": "علبة السرعة", "l_plate": "رقم التسجيل",
        "l_chassis": "رقم الهيكل", "l_km": "عداد المسافات", "km": "كلم",
        "l_holder": "صاحب الحساب", "l_bank": "البنك", "l_agency": "الوكالة",
        "l_rib": "رقم الحساب (RIB)", "l_to_pay": "المبلغ المطلوب دفعه",
        "l_price": "السعر الإجمالي", "l_paid": "المبلغ المدفوع (العربون)",
        "l_remaining": "المبلغ المتبقي",
        "id_note": "تجد في الصفحة الموالية نسخة من وثيقة هوية الزبون.",
        "id_page": "وثيقة الهوية - {name}",
        "canc_title": "محضر إلغاء عقد بالتراضي",
        "canc_intro": "بتاريخ {when}، اجتمع الطرفان وهما بكامل الأهلية المعتبرة، واتفقا بالتراضي التام على إلغاء عقد الوساطة رقم {cid} المبرم بينهما وفق الشروط التالية:",
        "canc_a1_t": "المادة 01: الأطراف",
        "canc_a1_b": "الطرف الأول: {company}\nالطرف الثاني (الزبون): {name}، رقم التعريف: {nid}\nالعنوان: {address}",
        "canc_a2_t": "المادة 02: موضوع الإلغاء",
        "canc_a2_b": "يتعلق هذا المحضر بإلغاء عقد الوساطة رقم {cid} الخاص بالسيارة: {car}، رقم الهيكل: {chassis}، رقم التسجيل: {plate}.",
        "canc_a3_t": "المادة 03: التسوية المالية",
        "canc_a3_b": "تم الاتفاق على إرجاع مبلغ {refund} للزبون، ويُعتبر العقد ملغىً بالتراضي من تاريخ التوقيع على هذا المحضر.",
        "canc_a4_t": "المادة 04: الخاتمة",
        "canc_a4_b": "حُرّر هذا المحضر ب{city} {when}، بحسن نية وباتفاق الطرفين، في نسختين أصليتين لكل طرف نسخة.",
        "canc_sig_company": "إمضاء وخاتم المؤسسة", "canc_sig_client": "إمضاء الزبون",
    },
    "fr": {
        "company": "Showroom DZ - Ramdane Djamel",
        "tagline": "Vente et achat de vehicules",
        "footer": "Adresse: Ramdane Djamel, Skikda, Algerie",
        "default_client": "client", "default_city": "Skikda",
        "contract_title": "Contrat de courtage commercial",
        "receipt_title": "Recu de paiement",
        "order_title": "Bon de commande", "pay_title": "Ordre de versement",
        "f_contract": "Contrat", "f_order": "Bon de commande", "f_pay": "Ordre de versement",
        "contract_no": "Contrat N°", "date": "Date", "time": "Heure",
        "when_dt": "le {d} à {t}", "when_d": "le {d}",
        "sig_company": "Signature et cachet", "sig_client": "Signature du client",
        "sig_cashier": "Signature du caissier", "sig_client_ok": "Signature du client",
        "sig_payer": "Signature du donneur d'ordre", "sig_bank": "Cachet de la banque",
        "t_client": "Informations du client",
        "t_client_payer": "Informations du client (donneur d'ordre)",
        "t_car": "Informations du vehicule", "t_car_ordered": "Vehicule commande",
        "t_car_pay": "Informations du vehicule",
        "t_bank": "Coordonnees bancaires", "t_amount": "Montant",
        "t_fin": "Details financiers", "h_amount": "Montant (DA)",
        "l_name": "Nom complet", "l_nid": "NIN",
        "l_birth": "Date et lieu de naissance", "l_address": "Adresse",
        "l_model": "Modele", "l_trim": "Version", "l_color": "Couleur",
        "l_gearbox": "Boite", "l_plate": "Immatriculation",
        "l_chassis": "Chassis", "l_km": "Kilometrage", "km": "km",
        "l_holder": "Titulaire", "l_bank": "Banque", "l_agency": "Agence",
        "l_rib": "N° compte (RIB)", "l_to_pay": "Montant a payer",
        "l_price": "Prix total", "l_paid": "Montant paye",
        "l_remaining": "Montant restant",
        "id_note": "Piece d'identite a la page suivante.",
        "id_page": "Piece d'identite - {name}",
        "canc_title": "PV de resiliation amiable",
        "canc_intro": "Le {when}, les deux parties ont convenu a l'amiable de resilier le contrat N° {cid} :",
        "canc_a1_t": "Article 01 : Parties",
        "canc_a1_b": "Premiere partie : {company}\nDeuxieme partie : {name}, NIN : {nid}\nAdresse : {address}",
        "canc_a2_t": "Article 02 : Objet",
        "canc_a2_b": "Resiliation du contrat N° {cid} - vehicule : {car}, chassis : {chassis}, immatriculation : {plate}.",
        "canc_a3_t": "Article 03 : Reglement",
        "canc_a3_b": "Restitution de {refund} au client. Contrat resilie a compter de la signature.",
        "canc_a4_t": "Article 04 : Cloture",
        "canc_a4_b": "Fait a {city} {when}, en deux exemplaires originaux.",
        "canc_sig_company": "Signature et cachet", "canc_sig_client": "Signature du client",
    },
}


def pdf_font():
    if os.path.exists(FONT_FILE):
        try:
            pdfmetrics.getFont("Sahel")
        except Exception:
            pdfmetrics.registerFont(TTFont("Sahel", FONT_FILE))
        return "Sahel"
    return FALLBACK_FONT


_glyph_cache = {}


def _has_glyph(fn, ch):
    key = (fn, ch)
    r = _glyph_cache.get(key)
    if r is None:
        try:
            r = ord(ch) in pdfmetrics.getFont(fn).face.charToGlyph
        except Exception:
            r = True
        _glyph_cache[key] = r
    return r


def _runs(shaped, fn):
    out = []
    for ch in shaped:
        if ch.isspace():
            f = out[-1][0] if out else fn
        elif _has_glyph(fn, ch):
            f = fn
        else:
            try:
                ch.encode("cp1252")
                f = FALLBACK_FONT
            except UnicodeEncodeError:
                base = "".join(c for c in unicodedata.normalize("NFKD", ch) if ord(c) < 128)
                if base:
                    ch, f = base, (fn if _has_glyph(fn, base) else FALLBACK_FONT)
                else:
                    f = fn
        if out and out[-1][0] == f:
            out[-1][1] += ch
        else:
            out.append([f, ch])
    return [(f, s) for f, s in out]


def shaped_width(shaped, fn, size):
    return sum(pdfmetrics.stringWidth(s, f, size) for f, s in _runs(shaped, fn))


def draw_text(cv, x, y, text, fn, size, align="left"):
    shaped = ar(text)
    runs = _runs(shaped, fn)
    total = sum(pdfmetrics.stringWidth(s, f, size) for f, s in runs)
    if align == "right":
        x -= total
    elif align == "center":
        x -= total / 2.0
    for f, s in runs:
        cv.setFont(f, size)
        cv.drawString(x, y, s)
        x += pdfmetrics.stringWidth(s, f, size)


def wrap_logical(text, maxw, fn, size):
    lines, cur = [], ""
    for w in clean_text(text).split(" "):
        t = (cur + " " + w).strip()
        if cur and shaped_width(ar(t), fn, size) > maxw:
            lines.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines or [""]


def draw_wrapped(cv, x, y, text, fn, size, align, maxw, leading):
    for raw in clean_text(text).split("\n"):
        for line in wrap_logical(raw, maxw, fn, size):
            draw_text(cv, x, y, line, fn, size, align)
            y -= leading
    return y


def cell(text, fn, size=9.5, align=TA_RIGHT, color=colors.black, maxw=300):
    lines = []
    for part in clean_text(text).split("\n"):
        lines.extend(wrap_logical(part, maxw, fn, size))
    html = []
    for ln in lines:
        seg = []
        for f, s in _runs(ar(ln), fn):
            s = xml_escape(s)
            seg.append(s if f == fn else '<font name="%s">%s</font>' % (f, s))
        html.append("".join(seg))
    st = ParagraphStyle("pdfcell", fontName=fn, fontSize=size, leading=size * 1.35,
                        alignment=align, textColor=color)
    return Paragraph("<br/>".join(html), st)


def pdf_info_table(title, rows, lang, fn, label_w=150, value_w=340, col_headers=None):
    rtl = lang == "ar"
    al = TA_RIGHT if rtl else TA_LEFT
    total = label_w + value_w
    header_bg = NAVY
    if WHITE_THEME_MODE:
        header_bg = colors.HexColor("#0B5394")
    if col_headers:
        lh, vh = col_headers
        lh_c = cell(lh, fn, 9.5, al, colors.white, label_w - 14)
        vh_c = cell(vh, fn, 9.5, al, colors.white, value_w - 14)
        head = [vh_c, lh_c] if rtl else [lh_c, vh_c]
    else:
        head = [cell(title, fn, 10, al, colors.white, total - 14), ""]
    data = [head]
    for label, value in rows:
        lc = cell(label, fn, 9.5, al, colors.black, label_w - 14)
        vc = cell(value, fn, 9.5, al, colors.black, value_w - 14)
        data.append([vc, lc] if rtl else [lc, vc])
    widths = [value_w, label_w] if rtl else [label_w, value_w]
    t = Table(data, colWidths=widths)
    style = [
        ("BACKGROUND", (0, 0), (1, 0), header_bg),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.5, GRID_C),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ZEBRA]),
    ]
    if not col_headers:
        style.append(("SPAN", (0, 0), (1, 0)))
    t.setStyle(TableStyle(style))
    return t


def place_tables(cv, tables, y, W, H, footer_fn, min_y=135):
    for t in tables:
        _, h = t.wrapOn(cv, W, H)
        if y - h < min_y:
            footer_fn()
            cv.showPage()
            y = H - 50
        t.drawOn(cv, 50, y - h)
        y -= h + 18
    return y


def pdf_edge(W, rtl):
    return (W - 50, "right") if rtl else (50, "left")


def pdf_header(cv, fn, W, H, lang, logo=True, company_info=None):
    T = PDF_TR[lang]
    rtl = lang == "ar"
    cv.setFillColor(NAVY)
    cv.rect(0, H - 85, W, 85, fill=1, stroke=0)
    cv.setFillColor(GOLD)
    cv.rect(0, H - 90, W, 5, fill=1, stroke=0)
    if WHITE_THEME_MODE:
        cv.setFillColor(colors.HexColor("#0B1F3A"))
    else:
        cv.setFillColor(colors.white)
    edge, al = pdf_edge(W, rtl)
    if company_info and company_info.get("name"):
        comp_name = company_info["name"]
    else:
        comp_name = T["company"]
    draw_text(cv, edge, H - 40, comp_name, fn, 18, al)
    if company_info:
        parts = []
        if company_info.get("rc"):
            parts.append("RC: " + company_info["rc"])
        if company_info.get("nif"):
            parts.append("NIF: " + company_info["nif"])
        if company_info.get("phone"):
            parts.append(company_info["phone"])
        info_line = "  |  ".join(parts) if parts else T["tagline"]
    else:
        info_line = T["tagline"]
    draw_text(cv, edge, H - 62, info_line, fn, 10, al)
    logo_path = None
    if company_info and company_info.get("logo") and os.path.exists(company_info["logo"]):
        logo_path = company_info["logo"]
    elif logo and os.path.exists(LOGO_FILE):
        logo_path = LOGO_FILE
    if logo_path:
        try:
            lx = 50 if rtl else W - 50 - 65
            cv.drawImage(logo_path, lx, H - 80, 65, 65, mask="auto", preserveAspectRatio=True)
        except Exception:
            pass
    cv.setFillColor(colors.black)


def pdf_footer(cv, fn, W, lang, company_info=None):
    cv.setStrokeColor(colors.HexColor("#CCCCCC"))
    cv.setLineWidth(0.5)
    cv.line(50, 50, W - 50, 50)
    cv.setFillColor(colors.black)
    if company_info:
        address = company_info.get("address_fr" if lang == "fr" else "address_ar")
        phone = company_info.get("phone", "")
        parts = [p for p in (address, phone) if p]
        footer_text = "  |  ".join(parts) if parts else PDF_TR[lang]["footer"]
    else:
        footer_text = PDF_TR[lang]["footer"]
    draw_text(cv, W / 2.0, 35, footer_text, fn, 9, "center")


def pdf_signatures(cv, fn, W, y_line, lang, first, second=None, line_len=240, text_dy=22):
    cv.setStrokeColor(colors.HexColor("#333333"))
    cv.setLineWidth(1.0)
    cv.setFillColor(colors.black)
    if lang == "ar":
        positions = [(W - 60, first, "right")]
        if second:
            positions.append((60, second, "left"))
    else:
        positions = [(60, first, "left")]
        if second:
            positions.append((W - 60, second, "right"))
    y_text = y_line - text_dy
    for x, txt, al in positions:
        if al == "right":
            cv.line(x - line_len, y_line, x, y_line)
        else:
            cv.line(x, y_line, x + line_len, y_line)
        draw_text(cv, x, y_text, txt, fn, 11, al)


def split_dt(value=None):
    dt, has_time = None, True
    if value:
        s = str(value).strip().split(".")[0].replace("T", " ")
        for f, ht in (("%Y-%m-%d %H:%M:%S", True), ("%Y-%m-%d %H:%M", True), ("%Y-%m-%d", False)):
            try:
                dt, has_time = datetime.datetime.strptime(s, f), ht
                break
            except ValueError:
                continue
        if dt is None:
            return clean_text(value), ""
    else:
        dt = datetime.datetime.now()
    return dt.strftime("%d/%m/%Y"), (dt.strftime("%H:%M") if has_time else "")


def contract_number(cid, cdate):
    d, _ = split_dt(cdate)
    parts = d.split("/")
    if len(parts) == 3:
        d = parts[2] + parts[1] + parts[0]
    else:
        d = re.sub(r"\D", "", d) or "00000000"
    return f"KS-{cid}-{d}"


def meta_line(T, rtl, cno, d, t):
    sep = ": " if rtl else " : "
    parts = ["%s%s%s" % (T["contract_no"], sep, cno), "%s%s%s" % (T["date"], sep, d)]
    if t:
        parts.append("%s%s%s" % (T["time"], sep, t))
    return "  |  ".join(parts)


def pdf_amount(value, lang, add_unit=False):
    s = clean_text(value).strip()
    if not s or s == "None":
        s = "0"
    if lang == "fr":
        s = re.sub(r"\s*مليون", " Millions", s)
    else:
        s = re.sub(r"(?i)\s*millions?\b", " مليون", s)
    if add_unit and re.fullmatch(r"[\d\s.,]+", s):
        s = "%s %s" % (s.strip(), TRANSLATIONS[lang]["million"])
    return s.strip()


def loc_amount(value, lang):
    s = clean_text(value).strip()
    if not s or s == "None":
        return s
    if lang == "fr":
        s = re.sub(r"\s*مليون", " Millions", s)
    else:
        s = re.sub(r"(?i)\s*millions?\b", " مليون", s)
    return s.strip()


def pick_name(name, name_fr, lang):
    name = clean_text(name).strip() if name not in (None, "None") else ""
    name_fr = clean_text(name_fr).strip() if name_fr not in (None, "None") else ""
    if lang == "fr":
        return name_fr or name
    return name or name_fr


_COLORS = [
    ("أبيض", "Blanc"), ("أسود", "Noir"), ("رمادي", "Gris"),
    ("رمادي غامق", "Gris fonce"), ("رمادي فاتح", "Gris clair"),
    ("رصاصي", "Gris anthracite"), ("فضي", "Argent"),
    ("أحمر", "Rouge"), ("عنابي", "Bordeaux"), ("أزرق", "Bleu"),
    ("أزرق غامق", "Bleu fonce"), ("كحلي", "Bleu marine"),
    ("سماوي", "Bleu ciel"), ("أخضر", "Vert"), ("أخضر غامق", "Vert fonce"),
    ("زيتي", "Vert olive"), ("أصفر", "Jaune"), ("برتقالي", "Orange"),
    ("بني", "Marron"), ("ذهبي", "Dore"), ("بيج", "Beige"),
    ("كريمي", "Creme"), ("بنفسجي", "Violet"), ("وردي", "Rose"),
    ("نحاسي", "Cuivre"), ("تركوازي", "Turquoise"),
]


def _ckey(v):
    s = clean_text(v).strip().lower()
    s = s.translate({ord(c): "ا" for c in "أإآ"}).replace("ى", "ي")
    s = "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", s)


_COLOR_AR2FR = {_ckey(a): f for a, f in _COLORS}
_COLOR_FR2AR = {_ckey(f): a for a, f in _COLORS}


def loc_color(v, lang):
    s = clean_text(v).strip() if v not in (None, "None") else ""
    if not s:
        return s
    k = _ckey(s)
    if lang == "fr":
        return _COLOR_AR2FR.get(k, s)
    return _COLOR_FR2AR.get(k, s)


def loc_gearbox(v, lang):
    s = clean_text(v).strip()
    if s in ("", "None"):
        return "-"
    low = s.lower()
    if low in ("أوتوماتيك", "automatique", "automatic", "auto"):
        return TRANSLATIONS[lang]["automatic"]
    if low in ("يدوي", "manuelle", "manuel", "manual"):
        return TRANSLATIONS[lang]["manual"]
    return s


def qr_payload(*pairs):
    return "\n".join("%s:%s" % (k, clean_text(v)) for k, v in pairs if v not in (None, "", "-"))


def draw_qr(cv, payload, W, y=60, size=58):
    def _render(text):
        w = QrCodeWidget(text, barLevel="M", barBorder=2)
        x0, y0, x1, y1 = w.getBounds()
        d = Drawing(size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
        d.add(w)
        renderPDF.draw(d, cv, (W - size) / 2.0, y)
    try:
        safe = clean_text(payload)
        safe = "".join(ch for ch in safe if unicodedata.category(ch) != "Cf")
        _render(safe)
    except Exception:
        pass


def draw_watermark(cv, W, H, company_info=None, alpha=0.07):
    watermark_logo = None
    if company_info and company_info.get("logo") and os.path.exists(company_info["logo"]):
        watermark_logo = company_info["logo"]
    elif os.path.exists(LOGO_FILE):
        watermark_logo = LOGO_FILE
    if not watermark_logo:
        return
    try:
        from PIL import Image as PILImage
        from reportlab.lib.utils import ImageReader
        import io
        im = PILImage.open(watermark_logo).convert("RGBA")
        r, g, b, a = im.split()
        im.putalpha(a.point(lambda v: int(v * alpha)))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        buf.seek(0)
        size = 400
        cv.drawImage(ImageReader(buf), (W - size) / 2, (H - size) / 2 - 20,
                     size, size, mask='auto', preserveAspectRatio=True)
    except Exception:
        pass


# =====================================================================
#  قاعدة البيانات
# =====================================================================
def init_db():
    conn = sqlite3.connect(get_db_path())
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS cars
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT, mileage TEXT, price TEXT, status INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS clients
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  full_name TEXT, national_id TEXT,
                  birth_info TEXT, address TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS contracts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  car_id INTEGER, client_id INTEGER,
                  contract_price TEXT, paid_amount TEXT,
                  remaining_amount TEXT, date TEXT)''')
    c.execute("PRAGMA table_info(contracts)")
    cols = [col[1] for col in c.fetchall()]
    if "paid_amount" not in cols:
        c.execute("ALTER TABLE contracts ADD COLUMN paid_amount TEXT")
    if "remaining_amount" not in cols:
        c.execute("ALTER TABLE contracts ADD COLUMN remaining_amount TEXT")
    c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    c.execute("PRAGMA table_info(cars)")
    cols = [col[1] for col in c.fetchall()]
    for extra in ("color", "gearbox", "trim", "plate", "chassis", "name_fr", "profit_margin"):
        if extra not in cols:
            c.execute(f"ALTER TABLE cars ADD COLUMN {extra} TEXT")
    c.execute("PRAGMA table_info(clients)")
    cols = [col[1] for col in c.fetchall()]
    if "full_name_fr" not in cols:
        c.execute("ALTER TABLE clients ADD COLUMN full_name_fr TEXT")
    if "address_fr" not in cols:
        c.execute("ALTER TABLE clients ADD COLUMN address_fr TEXT")
    conn.commit()
    conn.close()


# =====================================================================
#  مجلدات PDF
# =====================================================================
ROOT_AR = "الوثائق"
ROOT_FR = "francais"
DOC_FOLDERS = {
    "contract": {"ar": "العقود", "fr": "Contrats"},
    "cancel": {"ar": "إلغاء العقود", "fr": "Resiliations"},
    "pay": {"ar": "أوامر الدفع", "fr": "Ordres de versement"},
    "order": {"ar": "وصل الطلب", "fr": "Bons de commande"},
}


def doc_folder(doc_type, lang):
    base = os.path.join(app_root(), "pdf")
    root = os.path.join(base, ROOT_AR if lang == "ar" else ROOT_FR)
    sub = DOC_FOLDERS[doc_type][lang]
    path = os.path.join(root, sub)
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path


# =====================================================================
#  الترخيص
# =====================================================================
def get_device_id():
    try:
        conn = sqlite3.connect(get_db_path())
        row = conn.execute("SELECT value FROM settings WHERE key='device_id'").fetchone()
        if row and row[0]:
            conn.close()
            return row[0]
        dev_id = uuid.uuid4().hex[:16].upper()
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('device_id', ?)", (dev_id,))
        conn.commit()
        conn.close()
        return dev_id
    except Exception:
        return "UNKNOWN"


def check_activation(device_id, code):
    if not code or not device_id:
        return False
    if "PLACEHOLDER" in PUBLIC_KEY_PEM:
        return False
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.backends import default_backend
        public_key = serialization.load_pem_public_key(
            PUBLIC_KEY_PEM.encode("utf-8"),
            backend=default_backend()
        )
        cleaned = clean_text(code).replace(" ", "").replace("\n", "").replace("\r", "").replace("\t", "")
        padding_needed = (-len(cleaned)) % 4
        cleaned += "=" * padding_needed
        try:
            signature = base64.urlsafe_b64decode(cleaned)
        except Exception:
            signature = base64.b64decode(cleaned)
        public_key.verify(
            signature,
            device_id.strip().upper().encode("utf-8"),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256()
        )
        return True
    except Exception as e:
        print("Verify error:", e)
        return False


def is_activated():
    try:
        conn = sqlite3.connect(get_db_path())
        row = conn.execute("SELECT value FROM settings WHERE key='license_key'").fetchone()
        conn.close()
        if not row or not row[0]:
            return False
        return check_activation(get_device_id(), row[0])
    except Exception:
        return False


# =====================================================================
#  معالج الأعطال
# =====================================================================
class CrashHandler(ExceptionHandler):
    def handle_exception(self, inst):
        try:
            with open("crash_log.txt", "a", encoding="utf-8") as f:
                f.write("=" * 60 + "\n")
                f.write(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
                f.write("".join(traceback.format_exception(type(inst), inst, inst.__traceback__)))
                f.write("\n")
        except Exception:
            pass
        return ExceptionManager.PASS


ExceptionManager.add_handler(CrashHandler())


# =====================================================================
#  ArabicField
# =====================================================================
class ArabicField(MDTextField):
    def __init__(self, **kwargs):
        init_text = kwargs.pop('text', '') or ''
        self._logical = init_text
        self._updating = False
        super().__init__(text='', **kwargs)
        Clock.schedule_once(lambda dt: self._refresh(), 0)

    def _refresh(self, cursor_pos=None):
        self._updating = True
        try:
            txt = self._logical or ''
            if txt and is_arabic(txt):
                lines = txt.split('\n')
                reshaped_lines = []
                for line in lines:
                    if not line:
                        reshaped_lines.append('')
                        continue
                    if is_arabic(line):
                        try:
                            shaped = arabic_reshaper.reshape(clean_text(line))
                            reshaped_lines.append(get_display(shaped, base_dir='R'))
                        except Exception:
                            reshaped_lines.append(line)
                    else:
                        reshaped_lines.append(line)
                self.text = '\n'.join(reshaped_lines)
            else:
                self.text = txt
        except Exception:
            pass
        finally:
            self._updating = False
        pos = len(self.text) if cursor_pos is None else cursor_pos
        Clock.schedule_once(lambda dt: self._set_cursor(pos), 0)

    def _set_cursor(self, pos):
        try:
            self.cursor = (min(pos, len(self.text)), 0)
        except Exception:
            pass

    def insert_text(self, substring, from_undo=False):
        if self._updating:
            return
        sub = substring or ''
        if self.input_filter == 'int':
            sub = ''.join(c for c in sub if c.isdigit())
        elif self.input_filter == 'float':
            sub = ''.join(c for c in sub if c.isdigit() or c == '.')
        if not sub:
            return
        self._logical = (self._logical or '') + sub
        self._refresh()

    def do_backspace(self, from_undo=False, mode='bkspc'):
        if self._updating:
            return
        if self._logical:
            self._logical = self._logical[:-1]
        self._refresh()

    def delete_selection(self, from_undo=False):
        if self._updating:
            return
        self._logical = ''
        self._refresh()

    def get_logical(self):
        return self._logical or ''

    def set_logical(self, value):
        self._logical = value or ''
        self._refresh()


def field_val(field):
    if hasattr(field, 'get_logical'):
        return field.get_logical()
    return getattr(field, 'text', '') or ''


def set_field_val(field, value):
    if hasattr(field, 'set_logical'):
        field.set_logical(value)
    else:
        field.text = value or ''


# =====================================================================
#  KV (تم إزالة on_switch_tabs لمنع الانهيار)
# =====================================================================
KV = '''
<FormField@ArabicField>:
    mode: "rectangle"
    size_hint_y: None
    height: "58dp"
    font_size: "17sp"
    line_color_normal: 0.62, 0.68, 0.76, 1
    line_color_focus: 0.08, 0.45, 0.75, 1

<SearchField@MDTextField>:
    mode: "fill"
    fill_color_normal: 0.93, 0.95, 0.98, 1
    fill_color_focus: 0.90, 0.94, 0.99, 1
    line_color_normal: 0, 0, 0, 0
    line_color_focus: 0.08, 0.45, 0.75, 1
    line_width: 1.2
    size_hint_y: None
    height: "56dp"
    font_size: "15sp"
    radius: [18, 18, 18, 18]
    icon_left: "magnify"

<FormSpinner@Spinner>:
    size_hint_y: None
    height: "54dp"
    font_size: "17sp"
    color: 0.1, 0.15, 0.25, 1
    background_normal: ""
    background_down: ""
    background_color: 0, 0, 0, 0
    canvas.before:
        Color:
            rgba: 0.93, 0.96, 1, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(12)]
        Color:
            rgba: 0.08, 0.45, 0.75, 0.45
        Line:
            rounded_rectangle: (self.x, self.y, self.width, self.height, dp(12))
            width: 1.1

<FormLabel@MDLabel>:
    size_hint_y: None
    height: "22dp"
    font_size: "14sp"
    bold: True
    halign: "right" if app.current_lang == "ar" else "left"
    theme_text_color: "Custom"
    text_color: 0.08, 0.45, 0.75, 1

<DialogHeader>:
    orientation: "horizontal"
    size_hint_y: None
    height: "66dp"
    padding: "14dp", "8dp"
    spacing: "12dp"
    canvas.before:
        Color:
            rgba: 0.08, 0.45, 0.75, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(18)]
    MDIcon:
        icon: root.icon
        theme_text_color: "Custom"
        text_color: 1, 1, 1, 1
        font_size: "34sp"
        size_hint_x: None
        width: "44dp"
        pos_hint: {"center_y": .5}
    MDLabel:
        text: root.title
        halign: "right" if app.current_lang == "ar" else "left"
        theme_text_color: "Custom"
        text_color: 1, 1, 1, 1
        bold: True
        font_size: "20sp"

<CarDialogContent>:
    orientation: "vertical"
    spacing: "12dp"
    size_hint_y: None
    height: "1146dp"
    padding: [10, 6, 10, 10]
    DialogHeader:
        id: header
        icon: "car"
    FormLabel:
        text: app.trd("car_name_hint", app.current_lang)
    FormField:
        id: name_input
        icon_left: "car"
    FormLabel:
        text: app.trd("car_name_fr_hint", app.current_lang)
    FormField:
        id: name_fr_input
        icon_left: "translate"
    FormLabel:
        text: app.trd("mileage_hint", app.current_lang)
    FormField:
        id: mileage_input
        input_filter: "int"
        icon_left: "speedometer"
    FormLabel:
        text: app.trd("price_hint", app.current_lang)
    FormField:
        id: price_input
        icon_left: "cash"
    FormLabel:
        text: app.trd("profit_margin_hint", app.current_lang)
    FormField:
        id: profit_input
        icon_left: "chart-line"
    FormLabel:
        text: app.trd("trim_hint", app.current_lang)
    FormField:
        id: trim_input
        icon_left: "tag-outline"
    FormLabel:
        text: app.trd("color_hint", app.current_lang)
    FormField:
        id: color_input
        icon_left: "palette"
    FormLabel:
        text: app.trd("plate_hint", app.current_lang)
    FormField:
        id: plate_input
        icon_left: "card-text-outline"
    FormLabel:
        text: app.trd("chassis_hint", app.current_lang)
    FormField:
        id: chassis_input
        icon_left: "barcode"
    BoxLayout:
        orientation: "horizontal"
        spacing: "10dp"
        size_hint_y: None
        height: "54dp"
        MDLabel:
            text: app.trd("gearbox_label", app.current_lang)
            size_hint_x: 0.38
            font_size: "16sp"
            bold: True
            halign: "right" if app.current_lang == "ar" else "left"
            theme_text_color: "Custom"
            text_color: 0.08, 0.45, 0.75, 1
        FormSpinner:
            id: gearbox_spinner
            text: app.trd("not_specified", app.current_lang)
            values: [app.trd("not_specified", app.current_lang), app.trd("automatic", app.current_lang), app.trd("manual", app.current_lang)]
    BoxLayout:
        orientation: "horizontal"
        spacing: "10dp"
        size_hint_y: None
        height: "54dp"
        MDLabel:
            text: app.trd("status_label", app.current_lang)
            size_hint_x: 0.38
            font_size: "16sp"
            bold: True
            halign: "right" if app.current_lang == "ar" else "left"
            theme_text_color: "Custom"
            text_color: 0.08, 0.45, 0.75, 1
        FormSpinner:
            id: status_spinner
            text: app.trd("available", app.current_lang)
            values: [app.trd("available", app.current_lang), app.trd("reserved", app.current_lang), app.trd("sold", app.current_lang)]

<ClientDialogContent>:
    orientation: "vertical"
    spacing: "12dp"
    size_hint_y: None
    height: "722dp"
    padding: [10, 6, 10, 10]
    DialogHeader:
        id: header
        icon: "account-details"
    FormLabel:
        text: app.trd("client_name_hint", app.current_lang)
    FormField:
        id: name_input
        icon_left: "account"
    FormLabel:
        text: app.trd("client_name_fr_hint", app.current_lang)
    FormField:
        id: name_fr_input
        icon_left: "translate"
    FormLabel:
        text: app.trd("nid_hint", app.current_lang)
    FormField:
        id: nid_input
        input_filter: "int"
        icon_left: "card-account-details-outline"
    FormLabel:
        text: app.trd("birth_hint", app.current_lang)
    FormField:
        id: birth_input
        icon_left: "calendar"
    FormLabel:
        text: app.trd("address_hint", app.current_lang)
    FormField:
        id: address_input
        icon_left: "map-marker"
    FormLabel:
        text: app.trd("address_fr_hint", app.current_lang)
    FormField:
        id: address_fr_input
        icon_left: "translate"

<ContractDialogContent>:
    orientation: "vertical"
    spacing: "10dp"
    size_hint_y: None
    height: "726dp"
    padding: [10, 6, 10, 10]
    DialogHeader:
        id: header
        icon: "file-sign"
    FormLabel:
        text: app.trd("car_label", app.current_lang)
    FormSpinner:
        id: car_spinner
        text: app.trd("select_car", app.current_lang)
        values: []
        on_text: app.on_car_spinner_select(self.text)
    FormLabel:
        text: app.trd("client_label", app.current_lang)
    FormSpinner:
        id: client_spinner
        text: app.trd("select_client", app.current_lang)
        values: []
    FormLabel:
        text: app.trd("final_price_hint", app.current_lang)
    FormField:
        id: price_input
        icon_left: "cash"
    FormLabel:
        text: app.trd("profit_margin_hint", app.current_lang)
    FormField:
        id: profit_input
        icon_left: "chart-line"
    FormLabel:
        text: app.trd("paid_hint", app.current_lang)
    FormField:
        id: paid_input
        icon_left: "cash-check"
        on_text: app.calculate_remaining(self.text)
    FormLabel:
        text: app.trd("remaining_hint", app.current_lang)
    FormField:
        id: remaining_input
        icon_left: "cash-minus"
        readonly: True
    BoxLayout:
        size_hint_y: None
        height: "52dp"
        spacing: "10dp"
        MDFlatButton:
            text: app.trd("cancel", app.current_lang)
            font_size: "16sp"
            on_release: app.contract_dialog.dismiss()
        MDRaisedButton:
            text: app.trd("save_pdf", app.current_lang)
            font_size: "16sp"
            size_hint_x: 1
            md_bg_color: 0.08, 0.45, 0.75, 1
            on_release: app.save_contract(root)

<StatBox>:
    orientation: "vertical"
    radius: [16]
    elevation: 1
    padding: "8dp"
    md_bg_color: 1, 1, 1, 1
    MDLabel:
        text: root.value
        halign: "center"
        font_style: "H5"
        bold: True
        theme_text_color: "Custom"
        text_color: root.color
    MDLabel:
        text: root.label
        halign: "center"
        font_style: "Caption"
        theme_text_color: "Secondary"

<StatCard>:
    orientation: "vertical"
    size_hint_y: None
    height: "132dp"
    radius: [16]
    elevation: 2
    padding: "8dp"
    spacing: "2dp"
    md_bg_color: 1, 1, 1, 1
    MDBoxLayout:
        orientation: "vertical"
        size_hint_y: None
        height: "30dp"
        MDIcon:
            icon: root.icon
            halign: "center"
            font_size: "24sp"
            theme_text_color: "Custom"
            text_color: root.tint
    MDLabel:
        text: root.value
        halign: "center"
        valign: "middle"
        size_hint_y: None
        height: "28dp"
        font_size: "16sp"
        bold: True
        theme_text_color: "Custom"
        text_color: 0.10, 0.15, 0.25, 1
    MDLabel:
        text: root.unit
        halign: "center"
        valign: "middle"
        size_hint_y: None
        height: "14dp"
        font_size: "10sp"
        theme_text_color: "Custom"
        text_color: 0.55, 0.55, 0.60, 1
    MDLabel:
        text: root.label
        halign: "center"
        valign: "middle"
        size_hint_y: None
        height: "22dp"
        font_size: "10sp"
        theme_text_color: "Custom"
        text_color: 0.42, 0.42, 0.48, 1

<CarCard>:
    orientation: "horizontal"
    size_hint_y: None
    height: "124dp"
    radius: [16]
    elevation: 1
    padding: "14dp"
    spacing: "12dp"
    ripple_behavior: True
    md_bg_color: 1, 1, 1, 1
    MDLabel:
        text: root.status_text
        size_hint: None, None
        size: "74dp", "26dp"
        pos_hint: {"center_y": .5}
        halign: "center"
        font_size: "12sp"
        theme_text_color: "Custom"
        text_color: root.accent
        canvas.before:
            Color:
                rgba: root.accent[0], root.accent[1], root.accent[2], 0.15
            RoundedRectangle:
                pos: self.pos
                size: self.size
                radius: [13]
    MDBoxLayout:
        orientation: "vertical"
        spacing: "2dp"
        MDLabel:
            text: root.title
            halign: "right" if app.current_lang == "ar" else "left"
            valign: "middle"
            bold: True
            font_size: "16sp"
            shorten: True
            shorten_from: "right"
            text_size: self.width, None
        MDLabel:
            text: root.subtitle
            halign: "right" if app.current_lang == "ar" else "left"
            valign: "middle"
            font_size: "13sp"
            theme_text_color: "Secondary"
            shorten: True
            shorten_from: "right"
            text_size: self.width, None
        MDLabel:
            text: root.details
            halign: "right" if app.current_lang == "ar" else "left"
            valign: "middle"
            font_size: "12sp"
            theme_text_color: "Custom"
            text_color: 0.08, 0.45, 0.75, 1
            shorten: True
            shorten_from: "right"
            text_size: self.width, None
        MDLabel:
            text: root.details2
            halign: "right" if app.current_lang == "ar" else "left"
            valign: "middle"
            font_size: "12sp"
            theme_text_color: "Secondary"
            shorten: True
            shorten_from: "right"
            text_size: self.width, None
    MDIcon:
        icon: root.icon
        size_hint: None, None
        size: "40dp", "40dp"
        pos_hint: {"center_y": .5}
        theme_text_color: "Custom"
        text_color: root.accent

<ClientCard>:
    orientation: "horizontal"
    size_hint_y: None
    height: "76dp"
    radius: [16]
    elevation: 1
    padding: "14dp"
    spacing: "12dp"
    ripple_behavior: True
    md_bg_color: 1, 1, 1, 1
    MDBoxLayout:
        orientation: "vertical"
        spacing: "4dp"
        MDLabel:
            text: root.title
            halign: "right" if app.current_lang == "ar" else "left"
            bold: True
            font_style: "Subtitle1"
        MDLabel:
            text: root.subtitle
            halign: "right" if app.current_lang == "ar" else "left"
            font_style: "Caption"
            theme_text_color: "Secondary"
    MDIcon:
        icon: "account-circle"
        size_hint: None, None
        size: "44dp", "44dp"
        pos_hint: {"center_y": .5}
        theme_text_color: "Custom"
        text_color: 0.16, 0.5, 0.73, 1

<ActionTile>:
    orientation: "vertical"
    size_hint_y: None
    height: "88dp"
    radius: [16]
    elevation: 0
    padding: "6dp"
    spacing: "2dp"
    ripple_behavior: True
    md_bg_color: root.bg
    MDIcon:
        icon: root.icon
        halign: "center"
        size_hint_y: None
        height: "40dp"
        font_size: "30sp"
        theme_text_color: "Custom"
        text_color: root.tint
    MDLabel:
        text: root.label
        halign: "center"
        valign: "middle"
        font_size: "13sp"
        bold: True
        theme_text_color: "Custom"
        text_color: root.tint

<ContractCard>:
    orientation: "horizontal"
    size_hint_y: None
    height: "104dp"
    radius: [16]
    elevation: 1
    padding: "14dp", "10dp"
    spacing: "12dp"
    ripple_behavior: True
    md_bg_color: 1, 1, 1, 1
    MDBoxLayout:
        orientation: "vertical"
        spacing: "2dp"
        MDLabel:
            text: root.title
            halign: "right" if app.current_lang == "ar" else "left"
            valign: "middle"
            bold: True
            font_size: "16sp"
            shorten: True
            shorten_from: "right"
            text_size: self.width, None
        MDLabel:
            text: root.subtitle
            halign: "right" if app.current_lang == "ar" else "left"
            valign: "middle"
            font_size: "14sp"
            theme_text_color: "Secondary"
            shorten: True
            shorten_from: "right"
            text_size: self.width, None
        MDLabel:
            text: root.remaining
            halign: "right" if app.current_lang == "ar" else "left"
            valign: "middle"
            font_size: "13sp"
            theme_text_color: "Custom"
            text_color: 0.15, 0.55, 0.32, 1
            shorten: True
            shorten_from: "right"
            text_size: self.width, None
    MDIcon:
        icon: "file-pdf-box"
        size_hint: None, None
        size: "44dp", "44dp"
        pos_hint: {"center_y": .5}
        theme_text_color: "Custom"
        text_color: 0.75, 0.22, 0.17, 1

<LanguageSelector>:
    orientation: "horizontal"
    size_hint_y: None
    height: "48dp"
    spacing: "8dp"

    MDCard:
        orientation: "horizontal"
        size_hint_x: 0.5
        radius: [12]
        elevation: 2 if root.active_lang == "ar" else 0
        md_bg_color: (0.08, 0.45, 0.75, 1) if root.active_lang == "ar" else (0.95, 0.96, 0.98, 1)
        ripple_behavior: True
        padding: "8dp", 0
        on_release: root.select("ar")
        MDBoxLayout:
            orientation: "horizontal"
            spacing: "6dp"
            MDIcon:
                icon: "alpha-a-box"
                size_hint_x: None
                width: "26dp"
                pos_hint: {"center_y": .5}
                theme_text_color: "Custom"
                text_color: (1, 1, 1, 1) if root.active_lang == "ar" else (0.35, 0.42, 0.55, 1)
                font_size: "22sp"
            MDLabel:
                text: app.ar("العربية")
                font_name: app.font_file if app.font_file else "Roboto"
                valign: "middle"
                bold: True
                font_size: "14sp"
                theme_text_color: "Custom"
                text_color: (1, 1, 1, 1) if root.active_lang == "ar" else (0.35, 0.42, 0.55, 1)

    MDCard:
        orientation: "horizontal"
        size_hint_x: 0.5
        radius: [12]
        elevation: 2 if root.active_lang == "fr" else 0
        md_bg_color: (0.08, 0.45, 0.75, 1) if root.active_lang == "fr" else (0.95, 0.96, 0.98, 1)
        ripple_behavior: True
        padding: "8dp", 0
        on_release: root.select("fr")
        MDBoxLayout:
            orientation: "horizontal"
            spacing: "6dp"
            MDIcon:
                icon: "alpha-f-box"
                size_hint_x: None
                width: "26dp"
                pos_hint: {"center_y": .5}
                theme_text_color: "Custom"
                text_color: (1, 1, 1, 1) if root.active_lang == "fr" else (0.35, 0.42, 0.55, 1)
                font_size: "22sp"
            MDLabel:
                text: "Français"
                font_name: app.font_file if app.font_file else "Roboto"
                valign: "middle"
                bold: True
                font_size: "14sp"
                theme_text_color: "Custom"
                text_color: (1, 1, 1, 1) if root.active_lang == "fr" else (0.35, 0.42, 0.55, 1)

MDScreen:
    md_bg_color: 0.95, 0.96, 0.98, 1
    canvas.before:
        Color:
            rgba: 0.95, 0.96, 0.98, 1
        Rectangle:
            pos: self.pos
            size: self.size
    MDBoxLayout:
        orientation: "vertical"

        MDBoxLayout:
            orientation: "horizontal"
            size_hint_y: None
            height: "74dp"
            padding: "14dp", "8dp"
            spacing: "10dp"
            md_bg_color: 0.08, 0.20, 0.45, 1
            Image:
                source: app.logo_path if app.logo_path else ""
                size_hint_x: None
                width: "54dp"
                allow_stretch: True
                keep_ratio: True
            MDBoxLayout:
                orientation: "vertical"
                spacing: "2dp"
                MDLabel:
                    text: app.app_display_title
                    font_name: app.font_file
                    font_size: "20sp"
                    bold: True
                    color: 1, 1, 1, 1
                    halign: "right" if app.current_lang == "ar" else "left"
                    valign: "middle"
                    text_size: self.width, None
                MDLabel:
                    text: app.version_badge_text
                    font_name: app.font_file
                    font_size: "11sp"
                    bold: True
                    color: 1, 1, 1, 0.9
                    size_hint_y: None
                    height: "18dp"
                    halign: "right" if app.current_lang == "ar" else "left"
                    valign: "middle"
                    text_size: self.width, None

        MDBottomNavigation:
            panel_color: 1, 1, 1, 1
            selected_color_background: 0.08, 0.45, 0.75, 0.12
            text_color_active: 0.08, 0.45, 0.75, 1
            text_color_normal: 0.55, 0.55, 0.6, 1

            MDBottomNavigationItem:
                name: "cars_tab"
                text: app.trd("tab_cars", app.current_lang)
                icon: "car-side"
                MDFloatLayout:
                    MDBoxLayout:
                        orientation: "vertical"
                        padding: "12dp", "12dp", "12dp", 0
                        spacing: "10dp"
                        MDBoxLayout:
                            size_hint_y: None
                            height: "72dp"
                            spacing: "10dp"
                            StatBox:
                                id: stat_sold
                                label: app.trd("stat_sold", app.current_lang)
                                color: 0.75, 0.22, 0.17, 1
                            StatBox:
                                id: stat_reserved
                                label: app.trd("stat_reserved", app.current_lang)
                                color: 0.95, 0.61, 0.07, 1
                            StatBox:
                                id: stat_available
                                label: app.trd("stat_available", app.current_lang)
                                color: 0.15, 0.68, 0.38, 1
                        SearchField:
                            id: cars_search
                            hint_text: app.trd("search_cars_hint", app.current_lang)
                            on_text: app.search_cars(self.text)
                        ScrollView:
                            MDList:
                                id: cars_list
                                spacing: "10dp"
                                padding: 0, 0, 0, "90dp"
                    MDFloatingActionButton:
                        icon: "plus"
                        pos_hint: {"x": .04, "y": .03}
                        md_bg_color: 0.08, 0.45, 0.75, 1
                        on_release: app.show_add_car_dialog()
                    MDFloatingActionButton:
                        icon: "chart-bar"
                        pos_hint: {"right": .96, "y": .03}
                        md_bg_color: 0.55, 0.27, 0.68, 1
                        on_release: app.show_stats()

            MDBottomNavigationItem:
                name: "clients_tab"
                text: app.trd("tab_clients", app.current_lang)
                icon: "account-group"
                MDFloatLayout:
                    MDBoxLayout:
                        orientation: "vertical"
                        padding: "12dp", "12dp", "12dp", 0
                        spacing: "10dp"
                        SearchField:
                            id: clients_search
                            hint_text: app.trd("search_clients_hint", app.current_lang)
                            on_text: app.search_clients(self.text)
                        ScrollView:
                            MDList:
                                id: clients_list
                                spacing: "10dp"
                                padding: 0, 0, 0, "90dp"
                    MDFloatingActionButton:
                        icon: "account-plus"
                        pos_hint: {"x": .04, "y": .03}
                        md_bg_color: 0.08, 0.45, 0.75, 1
                        on_release: app.show_add_client_dialog()

            MDBottomNavigationItem:
                name: "sales_tab"
                text: app.trd("tab_contracts", app.current_lang)
                icon: "file-document-outline"
                MDFloatLayout:
                    MDBoxLayout:
                        orientation: "vertical"
                        padding: "12dp", "12dp", "12dp", 0
                        spacing: "10dp"
                        SearchField:
                            id: contracts_search
                            hint_text: app.trd("search_contracts_hint", app.current_lang)
                            on_text: app.search_contracts(self.text)
                        ScrollView:
                            MDList:
                                id: contracts_list
                                spacing: "10dp"
                                padding: 0, 0, 0, "90dp"
                    MDFloatingActionButton:
                        icon: "file-plus"
                        pos_hint: {"x": .04, "y": .03}
                        md_bg_color: 0.08, 0.45, 0.75, 1
                        on_release: app.show_add_contract_dialog()

            MDBottomNavigationItem:
                name: "settings_tab"
                text: app.trd("tab_settings", app.current_lang)
                icon: "cog"
                ScrollView:
                    canvas.before:
                        Color:
                            rgba: 0.95, 0.96, 0.98, 1
                        Rectangle:
                            pos: self.pos
                            size: self.size
                    MDBoxLayout:
                        orientation: "vertical"
                        adaptive_height: True
                        padding: "12dp"
                        spacing: "12dp"

                        MDCard:
                            orientation: "vertical"
                            adaptive_height: True
                            padding: "14dp"
                            spacing: "10dp"
                            radius: [16]
                            elevation: 2
                            md_bg_color: app.banner_bg_color
                            MDLabel:
                                text: app.upgrade_banner_text
                                bold: True
                                font_size: "14sp"
                                halign: "center"
                                valign: "middle"
                                theme_text_color: "Custom"
                                text_color: app.banner_text_color
                                size_hint_y: None
                                height: "40dp"
                                text_size: self.width, None
                            MDRaisedButton:
                                text: app.upgrade_btn_text
                                pos_hint: {"center_x": .5}
                                md_bg_color: app.banner_btn_color
                                size_hint_y: None
                                height: "48dp"
                                on_release: app.on_banner_btn_click()

                        MDCard:
                            orientation: "vertical"
                            adaptive_height: True
                            padding: "14dp"
                            spacing: "10dp"
                            radius: [16]
                            elevation: 1
                            md_bg_color: 1, 1, 1, 1
                            MDLabel:
                                text: app.trd("lang_section", app.current_lang)
                                bold: True
                                halign: "right" if app.current_lang == "ar" else "left"
                                size_hint_y: None
                                height: "32dp"
                            LanguageSelector:
                                id: lang_selector
                                active_lang: app.current_lang

                        MDCard:
                            orientation: "vertical"
                            adaptive_height: True
                            padding: "14dp"
                            spacing: "10dp"
                            radius: [16]
                            elevation: 1
                            md_bg_color: 1, 1, 1, 1
                            MDBoxLayout:
                                orientation: "horizontal"
                                size_hint_y: None
                                height: "32dp"
                                spacing: "8dp"
                                MDIcon:
                                    icon: "shield-lock"
                                    theme_text_color: "Custom"
                                    text_color: 0.75, 0.22, 0.17, 1
                                    size_hint_x: None
                                    width: "28dp"
                                MDLabel:
                                    text: app.trd("security_section", app.current_lang)
                                    bold: True
                                    halign: "right" if app.current_lang == "ar" else "left"
                                    theme_text_color: "Custom"
                                    text_color: 0.75, 0.22, 0.17, 1
                            MDRaisedButton:
                                text: app.security_btn_text
                                pos_hint: {"center_x": .5}
                                md_bg_color: 0.75, 0.22, 0.17, 1
                                on_release: app.show_security_dialog()

                        MDCard:
                            orientation: "vertical"
                            adaptive_height: True
                            padding: "14dp"
                            spacing: "10dp"
                            radius: [16]
                            elevation: 1
                            md_bg_color: 1, 1, 1, 1
                            MDBoxLayout:
                                orientation: "horizontal"
                                size_hint_y: None
                                height: "32dp"
                                spacing: "8dp"
                                MDIcon:
                                    icon: "domain"
                                    theme_text_color: "Custom"
                                    text_color: 0.55, 0.27, 0.68, 1
                                    size_hint_x: None
                                    width: "28dp"
                                MDLabel:
                                    text: app.trd("company_section", app.current_lang)
                                    bold: True
                                    halign: "right" if app.current_lang == "ar" else "left"
                                    theme_text_color: "Custom"
                                    text_color: 0.55, 0.27, 0.68, 1
                            MDRaisedButton:
                                text: app.trd("company_edit", app.current_lang)
                                pos_hint: {"center_x": .5}
                                md_bg_color: 0.55, 0.27, 0.68, 1
                                on_release: app.show_company_info_dialog()

                        MDCard:
                            orientation: "vertical"
                            adaptive_height: True
                            padding: "14dp"
                            spacing: "10dp"
                            radius: [16]
                            elevation: 1
                            md_bg_color: 1, 1, 1, 1
                            MDBoxLayout:
                                orientation: "horizontal"
                                size_hint_y: None
                                height: "32dp"
                                spacing: "8dp"
                                MDIcon:
                                    icon: "file-document-edit-outline"
                                    theme_text_color: "Custom"
                                    text_color: 0.0, 0.55, 0.62, 1
                                    size_hint_x: None
                                    width: "28dp"
                                MDLabel:
                                    text: app.trd("articles_section", app.current_lang)
                                    bold: True
                                    halign: "right" if app.current_lang == "ar" else "left"
                                    theme_text_color: "Custom"
                                    text_color: 0.0, 0.55, 0.62, 1
                            MDRaisedButton:
                                text: app.ar("تعديل البنود") if app.current_lang == "ar" else "Modifier les articles"
                                pos_hint: {"center_x": .5}
                                md_bg_color: 0.0, 0.55, 0.62, 1
                                on_release: app.show_articles_editor()
                            MDLabel:
                                text: app.trd("articles_hint", app.current_lang)
                                halign: "center"
                                font_size: "11sp"
                                theme_text_color: "Secondary"
                                size_hint_y: None
                                height: "32dp"
                                text_size: self.width, None

                        MDCard:
                            orientation: "vertical"
                            adaptive_height: True
                            padding: "14dp"
                            spacing: "10dp"
                            radius: [16]
                            elevation: 1
                            md_bg_color: 1, 1, 1, 1
                            MDBoxLayout:
                                orientation: "horizontal"
                                size_hint_y: None
                                height: "32dp"
                                spacing: "8dp"
                                MDIcon:
                                    icon: "bank"
                                    theme_text_color: "Custom"
                                    text_color: 0.08, 0.45, 0.75, 1
                                    size_hint_x: None
                                    width: "28dp"
                                MDLabel:
                                    text: app.trd("bank_section", app.current_lang)
                                    bold: True
                                    halign: "right" if app.current_lang == "ar" else "left"
                                    theme_text_color: "Custom"
                                    text_color: 0.08, 0.45, 0.75, 1
                            MDRaisedButton:
                                text: app.trd("bank_edit", app.current_lang)
                                pos_hint: {"center_x": .5}
                                md_bg_color: 0.08, 0.45, 0.75, 1
                                on_release: app.show_bank_info_dialog()

                        MDCard:
                            orientation: "vertical"
                            adaptive_height: True
                            padding: "14dp"
                            spacing: "10dp"
                            radius: [16]
                            elevation: 1
                            md_bg_color: 1, 1, 1, 1
                            MDLabel:
                                text: app.trd("export_data", app.current_lang)
                                bold: True
                                halign: "right" if app.current_lang == "ar" else "left"
                                size_hint_y: None
                                height: "32dp"
                            MDRaisedButton:
                                text: app.trd("export_cars", app.current_lang)
                                pos_hint: {"center_x": .5}
                                md_bg_color: 0.08, 0.45, 0.75, 1
                                on_release: app.export_csv("cars")
                            MDRaisedButton:
                                text: app.trd("export_clients", app.current_lang)
                                pos_hint: {"center_x": .5}
                                md_bg_color: 0.55, 0.27, 0.68, 1
                                on_release: app.export_csv("clients")
                            MDRaisedButton:
                                text: app.trd("export_contracts", app.current_lang)
                                pos_hint: {"center_x": .5}
                                md_bg_color: 0.0, 0.55, 0.62, 1
                                on_release: app.export_csv("contracts")

                        MDCard:
                            orientation: "vertical"
                            adaptive_height: True
                            padding: "14dp"
                            spacing: "10dp"
                            radius: [16]
                            elevation: 1
                            md_bg_color: 1, 1, 1, 1
                            MDLabel:
                                text: app.trd("db_section", app.current_lang)
                                bold: True
                                halign: "right" if app.current_lang == "ar" else "left"
                                size_hint_y: None
                                height: "32dp"
                            MDRaisedButton:
                                text: app.trd("backup_db", app.current_lang)
                                pos_hint: {"center_x": .5}
                                md_bg_color: 0.15, 0.55, 0.32, 1
                                on_release: app.backup_db()
                            
                            MDRaisedButton:
                                text: app.trd("restore_db", app.current_lang)
                                pos_hint: {"center_x": .5}
                                md_bg_color: 0.75, 0.22, 0.17, 1
                                on_release: app.start_restore()
                            MDLabel:
                                text: app.last_backup_text
                                halign: "center"
                                font_size: "11sp"
                                theme_text_color: "Secondary"
                                size_hint_y: None
                                height: "20dp"

                        MDCard:
                            orientation: "vertical"
                            adaptive_height: True
                            padding: "14dp"
                            spacing: "10dp"
                            radius: [16]
                            elevation: 1
                            md_bg_color: 1, 1, 1, 1
                            MDLabel:
                                text: app.trd("about_title", app.current_lang)
                                bold: True
                                halign: "right" if app.current_lang == "ar" else "left"
                                size_hint_y: None
                                height: "32dp"
                            MDRaisedButton:
                                text: app.trd("about_title", app.current_lang)
                                pos_hint: {"center_x": .5}
                                md_bg_color: 0.08, 0.45, 0.75, 1
                                on_release: app.show_about()
                            MDLabel:
                                text: "v" + app.get_app_version()
                                halign: "center"
                                font_size: "12sp"
                                theme_text_color: "Secondary"
'''
# =====================================================================
#  الأصناف
# =====================================================================
class DialogHeader(MDBoxLayout):
    icon = StringProperty("car")
    title = StringProperty("")

    def on_kv_post(self, base_widget):
        app = MDApp.get_running_app()
        if app is not None and app.current_lang == "ar":
            kids = list(self.children)
            self.clear_widgets()
            for w in kids:
                self.add_widget(w)


class BigDialog(MDDialog):
    def update_width(self, *args):
        from kivy.core.window import Window
        self.width = min(Window.width - dp(16), dp(640))


class CarDialogContent(BoxLayout): pass
class ClientDialogContent(BoxLayout): pass
class ContractDialogContent(BoxLayout): pass


class StatBox(MDCard):
    value = StringProperty("0")
    label = StringProperty("")
    color = ListProperty([0, 0, 0, 1])


class StatCard(MDCard):
    icon = StringProperty("chart-box")
    value = StringProperty("0")
    unit = StringProperty("")
    label = StringProperty("")
    tint = ListProperty([0, 0, 0, 1])


class CarCard(MDCard):
    car_id = NumericProperty()
    title = StringProperty()
    subtitle = StringProperty()
    status_text = StringProperty()
    details = StringProperty()
    details2 = StringProperty()
    icon = StringProperty("car")
    accent = ListProperty([0, 0, 0, 1])


class ClientCard(MDCard):
    client_id = NumericProperty()
    title = StringProperty()
    subtitle = StringProperty()


class ActionTile(MDCard):
    label = StringProperty()
    icon = StringProperty()
    tint = ListProperty([0, 0, 0, 1])
    bg = ListProperty([1, 1, 1, 1])


class ContractCard(MDCard):
    contract_id = NumericProperty()
    title = StringProperty()
    subtitle = StringProperty()
    remaining = StringProperty()


class LanguageSelector(MDBoxLayout):
    active_lang = StringProperty("ar")

    def select(self, lang_code):
        from kivymd.app import MDApp
        app = MDApp.get_running_app()
        if not app:
            return
        if lang_code == self.active_lang:
            return
        app.change_language_by_code(lang_code)
        self.active_lang = lang_code


# =====================================================================
#  التطبيق
# =====================================================================
class AutoManagerApp(MDApp):
    font_file = FONT_FILE if os.path.exists(FONT_FILE) else "Roboto"
    logo_path = StringProperty("")
    app_display_title = StringProperty("Showroom Manager")
    current_lang = StringProperty("ar")

    version_badge_text = StringProperty("FREE")
    upgrade_banner_text = StringProperty("")
    upgrade_btn_text = StringProperty("")
    banner_bg_color = ListProperty([0.98, 0.95, 0.88, 1])
    banner_text_color = ListProperty([0.75, 0.22, 0.17, 1])
    banner_btn_color = ListProperty([0.15, 0.55, 0.32, 1])
    security_btn_text = StringProperty("")
    last_backup_text = StringProperty("")

    car_dialog = None
    car_action_dialog = None
    current_car_id = None
    client_dialog = None
    client_action_dialog = None
    current_client_id = None
    contract_dialog = None
    contract_action_dialog = None
    current_contract_id = None
    contract_edit_id = None
    active_contract_content = None
    cancel_dialog = None
    bank_dialog = None
    company_dialog = None
    upgrade_dialog = None
    lock_dialog = None
    security_dialog = None
    recovery_dialog = None
    articles_dialog = None
    _edited_articles = None

    def tr(self, key, lang=None):
        l = lang or self.current_lang
        return TRANSLATIONS.get(l, {}).get(key, key)

    def ar(self, text):
        return ar(text)

    def ar_markup(self, text):
        return ar_markup(text)

    def trd(self, key, lang=None):
        return ar(self.tr(key, lang))

    def get_app_version(self):
        return APP_VERSION

    def is_premium(self):
        try:
            return is_activated()
        except Exception:
            return False

    def car_count(self):
        try:
            conn = sqlite3.connect(get_db_path())
            cnt = conn.execute("SELECT COUNT(*) FROM cars").fetchone()[0]
            conn.close()
            return cnt
        except Exception:
            return 0

    def client_count(self):
        try:
            conn = sqlite3.connect(get_db_path())
            cnt = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
            conn.close()
            return cnt
        except Exception:
            return 0

    def contract_count(self):
        try:
            conn = sqlite3.connect(get_db_path())
            cnt = conn.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]
            conn.close()
            return cnt
        except Exception:
            return 0

    def refresh_premium_ui(self):
        try:
            premium = self.is_premium()
            if premium:
                self.version_badge_text = "PREMIUM"
                if self.current_lang == "ar":
                    self.upgrade_banner_text = self.ar("النسخة الكاملة مفعّلة")
                    self.upgrade_btn_text = self.ar("إغلاق التنبيه")
                else:
                    self.upgrade_banner_text = "Version complete active"
                    self.upgrade_btn_text = "Fermer"
                self.banner_bg_color = [0.88, 0.97, 0.90, 1]
                self.banner_text_color = [0.15, 0.55, 0.32, 1]
                self.banner_btn_color = [0.55, 0.55, 0.60, 1]
            else:
                self.version_badge_text = "FREE"
                n = self.car_count()
                if self.current_lang == "ar":
                    self.upgrade_banner_text = self.ar(
                        f"نسخة مجانية: {n} من {FREE_LIMIT_CARS} سيارة")
                    self.upgrade_btn_text = self.ar("ترقية الآن")
                else:
                    self.upgrade_banner_text = (
                        f"Version gratuite: {n} sur {FREE_LIMIT_CARS}")
                    self.upgrade_btn_text = "Mettre a niveau"
                self.banner_bg_color = [0.98, 0.95, 0.88, 1]
                self.banner_text_color = [0.75, 0.22, 0.17, 1]
                self.banner_btn_color = [0.15, 0.55, 0.32, 1]
        except Exception as e:
            print("refresh_premium_ui error:", e)

    def refresh_security_btn(self):
        try:
            has_pin = bool(get_pin_hash())
            if self.current_lang == "ar":
                self.security_btn_text = (
                    self.ar("تغيير كلمة السر") if has_pin
                    else self.ar("تعيين كلمة السر"))
            else:
                self.security_btn_text = (
                    "Changer le code" if has_pin
                    else "Definir un code")
        except Exception:
            self.security_btn_text = ""

    def refresh_last_backup_text(self):
        try:
            last = self.get_setting("last_auto_backup") or ""
            if last:
                try:
                    dt = datetime.datetime.fromisoformat(last)
                    if self.current_lang == "ar":
                        self.last_backup_text = self.ar(
                            f"آخر نسخة تلقائية: {dt.strftime('%d/%m/%Y %H:%M')}")
                    else:
                        self.last_backup_text = (
                            f"Derniere sauvegarde: {dt.strftime('%d/%m/%Y %H:%M')}")
                except Exception:
                    self.last_backup_text = ""
            else:
                self.last_backup_text = (
                    self.ar("لم تُنشأ نسخة بعد")
                    if self.current_lang == "ar"
                    else "Aucune sauvegarde")
        except Exception:
            self.last_backup_text = ""

    def on_banner_btn_click(self, *args):
        try:
            if self.is_premium():
                self.notify(self.ar("التطبيق مفعّل") if self.current_lang == "ar"
                            else "Application active")
            else:
                self.show_upgrade_dialog("")
        except Exception as e:
            print("banner click error:", e)

    def style_form(self, content, title_key, icon):
        content.ids.header.title = self.trd(title_key)
        content.ids.header.icon = icon

    def btn_cancel(self, cb):
        return MDFlatButton(text=self.trd("cancel"), font_size="16sp", on_release=cb)

    def btn_save(self, key, cb):
        return MDRaisedButton(text=self.trd(key), font_size="16sp",
                              md_bg_color=(0.08, 0.45, 0.75, 1), on_release=cb)

    def _is_opt(self, text, key):
        raw = self.tr(key)
        return str(text) in (raw, ar(raw))

    def _spinner_status_code(self, spinner):
        try:
            txt = clean_text(spinner.text)
            vals = list(spinner.values)
            for i, v in enumerate(vals):
                if v == spinner.text:
                    return i + 1
            cleaned = [clean_text(v) for v in vals]
            if txt in cleaned:
                return cleaned.index(txt) + 1
        except Exception:
            pass
        return 1

    def notify(self, text):
        msg = clean_text(text)
        if not IS_ANDROID:
            msg = ar(msg)
        toast(msg)

    def change_language(self, lang_text):
        new_lang = "ar" if ("العربية" in str(lang_text) or ar("العربية") == str(lang_text)) else "fr"
        self.change_language_by_code(new_lang)

    def change_language_by_code(self, lang_code):
        if lang_code not in ("ar", "fr"):
            return
        if lang_code == self.current_lang:
            return
        self.current_lang = lang_code
        try:
            conn = sqlite3.connect(get_db_path())
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('lang', ?)", (lang_code,))
            conn.commit()
            conn.close()
        except Exception:
            pass
        self.refresh_premium_ui()
        self.refresh_security_btn()
        self.refresh_last_backup_text()
        self.load_all_data()
        self.notify(self.tr("lang_changed"))

    def build(self):
        from kivy.core.window import Window
        Window.clearcolor = (0.95, 0.96, 0.98, 1)
        request_android_permissions()
        self.theme_cls.theme_style = "Light"
        self.theme_cls.primary_palette = "Blue"
        try:
            init_db()
        except Exception as e:
            print("init_db error:", e)
        return Builder.load_string(KV)

    def load_all_data(self):
        try: self.load_cars()
        except Exception as e: print("load_cars:", e)
        try: self.load_clients()
        except Exception as e: print("load_clients:", e)
        try: self.load_contracts()
        except Exception as e: print("load_contracts:", e)

    def on_start(self):
        try:
            self.load_settings()
            self.refresh_app_logo()
            self.refresh_app_title()
            self.refresh_premium_ui()
            self.refresh_security_btn()
            self.refresh_last_backup_text()
            self.load_all_data()

            if get_pin_hash():
                self.show_lock_screen()
            else:
                Clock.schedule_once(lambda dt: self.check_welcome(), 1.0)

            Clock.schedule_once(lambda dt: self.auto_backup(), 5)
            Clock.schedule_once(lambda dt: self.cleanup_old_backups(), 6)
        except Exception as e:
            print("on_start error:", e)
            traceback.print_exc()

    def refresh_app_logo(self):
        try:
            logo = self.get_setting("company_logo")
            if logo and os.path.exists(logo):
                self.logo_path = logo
                return
        except Exception:
            pass
        if os.path.exists(LOGO_FILE):
            self.logo_path = LOGO_FILE
        else:
            self.logo_path = ""

    def refresh_app_title(self):
        try:
            name = self.get_setting("company_name")
            if name and clean_text(name).strip():
                self.app_display_title = clean_text(name).strip()
                return
        except Exception:
            pass
        self.app_display_title = self.tr("app_title")

    def check_welcome(self):
        seen = self.get_setting("welcome_seen")
        if not seen:
            self.show_welcome_dialog()
            try:
                conn = sqlite3.connect(get_db_path())
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('welcome_seen', '1')")
                conn.commit()
                conn.close()
            except Exception:
                pass

    # ========== شاشة القفل PIN ==========
    def show_lock_screen(self):
        L = self.current_lang
        title_txt = (self.ar("أدخل كلمة السر للدخول") if L == "ar"
                     else "Entrez le code d'acces")
        btn_txt = self.ar("دخول") if L == "ar" else "Entrer"
        forgot_txt = self.trd("forgot_pin")

        box = MDBoxLayout(orientation="vertical", size_hint_y=None,
                          spacing=dp(14), padding=[dp(20), dp(20), dp(20), dp(20)],
                          adaptive_height=True)
        box.add_widget(MDLabel(
            text=title_txt,
            size_hint_y=None, height=dp(36), bold=True,
            font_size="16sp", halign="center",
            theme_text_color="Custom", text_color=(0.08, 0.45, 0.75, 1)))

        pin_field = MDTextField(mode="rectangle", font_size="22sp",
                                password=True, halign="center",
                                icon_left="lock", input_filter="int")
        box.add_widget(pin_field)

        status_lbl = MDLabel(
            text="", size_hint_y=None, height=dp(22),
            halign="center", font_size="12sp",
            theme_text_color="Custom", text_color=(0.75, 0.22, 0.17, 1))
        box.add_widget(status_lbl)

        remaining = get_lock_until()
        if remaining > 0:
            status_lbl.text = (self.ar(f"{self.tr('locked_for')}{remaining} {self.tr('seconds')}")
                               if L == "ar"
                               else f"{self.tr('locked_for')}{remaining} {self.tr('seconds')}")

        def update_status_tick():
            rem = get_lock_until()
            if rem > 0:
                status_lbl.text = (
                    self.ar(f"{self.tr('locked_for')}{rem} {self.tr('seconds')}")
                    if L == "ar"
                    else f"{self.tr('locked_for')}{rem} {self.tr('seconds')}")
                return True
            return False

        def check_pin(_=None):
            if get_lock_until() > 0:
                update_status_tick()
                return
            entered = (pin_field.text or "").strip()
            if not entered:
                self.notify(self.ar("الرجاء إدخال كلمة السر") if L == "ar"
                            else "Entrez le code")
                return
            if hash_pin(entered) == get_pin_hash():
                reset_fail_counter()
                self.lock_dialog.dismiss()
                self.lock_dialog = None
                self.load_all_data()
                self.refresh_premium_ui()
                Clock.schedule_once(lambda dt: self.check_welcome(), 0.5)
            else:
                lock_sec = register_fail()
                rem = get_lock_until()
                fails = get_fail_count()
                if lock_sec > 0:
                    status_lbl.text = (
                        self.ar(f"{self.tr('locked_for')}{rem} {self.tr('seconds')}")
                        if L == "ar"
                        else f"{self.tr('locked_for')}{rem} {self.tr('seconds')}")
                else:
                    left = max(0, 5 - fails)
                    status_lbl.text = (
                        self.ar(f"{self.tr('wrong_pin_n')}{left}")
                        if L == "ar"
                        else f"{self.tr('wrong_pin_n')}{left}")
                pin_field.text = ""

        box.add_widget(MDRaisedButton(
            text=btn_txt,
            md_bg_color=(0.08, 0.45, 0.75, 1),
            size_hint_y=None, height=dp(52),
            pos_hint={"center_x": 0.5},
            on_release=check_pin))

        def show_recovery(_=None):
            Clock.schedule_once(lambda dt: self.show_recovery_dialog(), 0.1)

        box.add_widget(MDFlatButton(
            text=forgot_txt,
            pos_hint={"center_x": 0.5},
            on_release=show_recovery))

        self.lock_dialog = BigDialog(
            title=self.trd("app_title"),
            type="custom",
            content_cls=box,
            auto_dismiss=False,
        )
        self.lock_dialog.open()
        Clock.schedule_once(lambda dt: setattr(pin_field, 'focus', True), 0.3)

        def _tick(dt):
            if self.lock_dialog is None:
                return
            try:
                still_open = bool(self.lock_dialog._window)
            except Exception:
                still_open = False
            if not still_open:
                return
            if update_status_tick():
                Clock.schedule_once(_tick, 1)

        if remaining > 0:
            Clock.schedule_once(_tick, 1)

    # ========== نافذة استرجاع كلمة السر ==========
    def show_recovery_dialog(self):
        from urllib.parse import quote
        L = self.current_lang
        device_id = get_device_id()

        box = MDBoxLayout(orientation="vertical", size_hint_y=None,
                          spacing=dp(10), padding=[dp(14), dp(10), dp(14), dp(14)],
                          adaptive_height=True)

        msg_lbl = MDLabel(
            text=self.trd("forgot_pin_msg"),
            size_hint_y=None, font_size="13sp",
            halign="right" if L == "ar" else "left",
            theme_text_color="Custom", text_color=(0.15, 0.15, 0.20, 1))
        msg_lbl.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
        msg_lbl.bind(texture_size=lambda i, ts: setattr(i, "height", ts[1] + 10))
        box.add_widget(msg_lbl)

        did_field = MDTextField(text=device_id, readonly=True, mode="rectangle",
                                font_size="14sp", icon_left="identifier",
                                halign="center")
        box.add_widget(did_field)

        def copy_did(_=None):
            try:
                Clipboard.copy(device_id)
                self.notify(self.tr("copied_ok"))
            except Exception:
                pass

        def send_wa(_=None):
            try:
                from kivy.utils import platform
                msg = f"طلب رمز استرجاع كلمة السر. معرّف الجهاز: {device_id}"
                url = "https://wa.me/213553762791?text=" + quote(msg)
                if platform == "android":
                    from jnius import autoclass, cast
                    PythonActivity = autoclass('org.kivy.android.PythonActivity')
                    Intent = autoclass('android.content.Intent')
                    Uri = autoclass('android.net.Uri')
                    String = autoclass('java.lang.String')
                    intent = Intent(Intent.ACTION_VIEW)
                    intent.setData(Uri.parse(url))
                    try:
                        PythonActivity.mActivity.startActivity(intent)
                    except Exception:
                        chooser = Intent.createChooser(
                            intent, cast('java.lang.CharSequence', String("Ouvrir")))
                        PythonActivity.mActivity.startActivity(chooser)
                else:
                    Clipboard.copy(url)
                    self.notify(self.tr("copied_ok"))
            except Exception as e:
                print("WA recovery err:", e)
                self.notify(f"Error: {str(e)[:40]}")

        row = MDBoxLayout(orientation="horizontal", size_hint_y=None,
                          height=dp(46), spacing=dp(8))
        row.add_widget(MDRaisedButton(
            text=self.trd("copy_id_short"),
            md_bg_color=(0.08, 0.45, 0.75, 1),
            on_release=copy_did))
        row.add_widget(MDRaisedButton(
            text="WhatsApp",
            md_bg_color=(0.15, 0.68, 0.38, 1),
            on_release=send_wa))
        box.add_widget(row)

        code_field = MDTextField(mode="rectangle", font_size="16sp",
                                 icon_left="key",
                                 hint_text=self.trd("recovery_code_hint"),
                                 halign="center")
        box.add_widget(code_field)

        def on_cancel_recovery(_=None):
            try:
                self.recovery_dialog.dismiss()
            except Exception:
                pass
            self.recovery_dialog = None
            try:
                if self.lock_dialog:
                    self.lock_dialog.dismiss()
            except Exception:
                pass
            self.lock_dialog = None
            Clock.schedule_once(lambda dt: self.show_lock_screen(), 0.3)

        def apply_recovery(_=None):
            entered = (code_field.text or "").strip()
            if check_recovery_code(device_id, entered):
                clear_pin()
                try:
                    self.recovery_dialog.dismiss()
                except Exception:
                    pass
                self.recovery_dialog = None
                try:
                    if self.lock_dialog:
                        self.lock_dialog.dismiss()
                except Exception:
                    pass
                self.lock_dialog = None
                self.refresh_security_btn()
                self.notify(self.tr("recovery_ok"))
                Clock.schedule_once(lambda dt: self.show_security_dialog(), 0.5)
            else:
                self.notify(self.tr("recovery_bad"))

        self.recovery_dialog = self.dlg(
            title=self.trd("forgot_pin_title"),
            type="custom",
            content_cls=self.wrap_dialog(box),
            buttons=[
                MDFlatButton(text=self.trd("cancel"),
                             on_release=on_cancel_recovery),
                MDRaisedButton(text=self.trd("verify"),
                               md_bg_color=(0.15, 0.55, 0.32, 1),
                               on_release=apply_recovery),
            ])
        self.recovery_dialog.open()

    # ========== حماية التطبيق ==========
    def show_security_dialog(self):
        has_pin = bool(get_pin_hash())
        L = self.current_lang

        if L == "ar":
            T_CURRENT  = "كلمة السر الحالية"
            T_NEW      = "كلمة السر الجديدة (4-6 أرقام)"
            T_CONFIRM  = "تأكيد كلمة السر"
            T_SAVE     = "حفظ"
            T_CANCEL   = "إلغاء"
            T_REMOVE   = "إزالة كلمة السر"
            T_TITLE    = "حماية التطبيق"
            T_ERR_OLD  = "كلمة السر الحالية غير صحيحة"
            T_ERR_LEN  = "كلمة السر يجب أن تكون 4-6 أرقام"
            T_ERR_MIS  = "كلمتا السر غير متطابقتين"
            T_OK       = "تم حفظ كلمة السر"
            T_FAIL     = "فشل الحفظ"
            T_REMOVED  = "تم إلغاء كلمة السر"
        else:
            T_CURRENT  = "Code actuel"
            T_NEW      = "Nouveau code (4-6 chiffres)"
            T_CONFIRM  = "Confirmer le code"
            T_SAVE     = "Enregistrer"
            T_CANCEL   = "Annuler"
            T_REMOVE   = "Supprimer le code"
            T_TITLE    = "Securite de l'application"
            T_ERR_OLD  = "Code actuel incorrect"
            T_ERR_LEN  = "Le code doit contenir 4-6 chiffres"
            T_ERR_MIS  = "Les deux codes ne correspondent pas"
            T_OK       = "Code enregistre"
            T_FAIL     = "Echec de l'enregistrement"
            T_REMOVED  = "Code supprime"

        def _txt(s):
            return self.ar(s) if L == "ar" else s

        box = MDBoxLayout(orientation="vertical", size_hint_y=None,
                          spacing=dp(10), padding=[dp(14), dp(10), dp(14), dp(14)],
                          adaptive_height=True)
        old_pin = None
        if has_pin:
            box.add_widget(MDLabel(text=_txt(T_CURRENT),
                                   size_hint_y=None, height=dp(24), bold=True,
                                   font_size="13sp",
                                   halign="right" if L == "ar" else "left",
                                   theme_text_color="Custom",
                                   text_color=(0.08, 0.45, 0.75, 1)))
            old_pin = MDTextField(mode="rectangle", font_size="18sp",
                                  password=True, halign="center",
                                  input_filter="int", icon_left="lock")
            box.add_widget(old_pin)

        box.add_widget(MDLabel(text=_txt(T_NEW),
                               size_hint_y=None, height=dp(24), bold=True,
                               font_size="13sp",
                               halign="right" if L == "ar" else "left",
                               theme_text_color="Custom",
                               text_color=(0.08, 0.45, 0.75, 1)))
        new_pin = MDTextField(mode="rectangle", font_size="18sp",
                              password=True, halign="center",
                              input_filter="int", icon_left="key")
        box.add_widget(new_pin)

        box.add_widget(MDLabel(text=_txt(T_CONFIRM),
                               size_hint_y=None, height=dp(24), bold=True,
                               font_size="13sp",
                               halign="right" if L == "ar" else "left",
                               theme_text_color="Custom",
                               text_color=(0.08, 0.45, 0.75, 1)))
        confirm_pin = MDTextField(mode="rectangle", font_size="18sp",
                                  password=True, halign="center",
                                  input_filter="int", icon_left="key-check")
        box.add_widget(confirm_pin)

        def save_pin(_=None):
            new = (new_pin.text or "").strip()
            confirm = (confirm_pin.text or "").strip()
            if has_pin:
                old = (old_pin.text or "").strip()
                if hash_pin(old) != get_pin_hash():
                    self.notify(_txt(T_ERR_OLD))
                    return
            if len(new) < 4 or len(new) > 6:
                self.notify(_txt(T_ERR_LEN))
                return
            if new != confirm:
                self.notify(_txt(T_ERR_MIS))
                return
            if set_pin_hash(new):
                self.security_dialog.dismiss()
                self.security_dialog = None
                self.refresh_security_btn()
                self.notify(_txt(T_OK))
            else:
                self.notify(_txt(T_FAIL))

        def remove_pin(_=None):
            if not has_pin:
                return
            old = (old_pin.text or "").strip()
            if hash_pin(old) != get_pin_hash():
                self.notify(_txt(T_ERR_OLD))
                return
            if clear_pin():
                self.security_dialog.dismiss()
                self.security_dialog = None
                self.refresh_security_btn()
                self.notify(_txt(T_REMOVED))

        buttons = [MDFlatButton(text=_txt(T_CANCEL),
                                on_release=lambda x: self.security_dialog.dismiss())]
        if has_pin:
            buttons.append(MDFlatButton(
                text=_txt(T_REMOVE),
                text_color=(1, 0, 0, 1),
                on_release=remove_pin))
        buttons.append(MDRaisedButton(
            text=_txt(T_SAVE),
            md_bg_color=(0.08, 0.45, 0.75, 1),
            on_release=save_pin))

        self.security_dialog = self.dlg(
            title=_txt(T_TITLE),
            type="custom",
            content_cls=self.wrap_dialog(box),
            buttons=buttons)
        self.security_dialog.open()

    # ========== محرر بنود العقد ==========
    def show_articles_editor(self):
        from kivy.uix.scrollview import ScrollView
        from kivy.core.window import Window
        L = self.current_lang
        self._edited_articles = list(get_contract_articles(L))

        if L == "ar":
            TXT_TITLE      = "بنود العقد (العربية)"
            TXT_VARIABLES  = ("المتغيرات المتاحة: {name} {nid} {birth} {address} "
                              "{car} {km} {trim} {color} {gearbox} {plate} "
                              "{chassis} {price} {when} {company} {city}")
            TXT_ADD        = "إضافة بند"
            TXT_RESET      = "استرجاع الافتراضي"
            TXT_EXPORT     = "تصدير ملف"
            TXT_IMPORT     = "استيراد ملف"
            TXT_SAVE       = "حفظ"
            TXT_CANCEL     = "إلغاء"
            TXT_DELETE     = "حذف"
            TXT_TITLE_HINT = "عنوان البند"
            TXT_BODY_HINT  = "نص البند"
            TXT_IMPORTED   = "تم الاستيراد — اضغط حفظ"
            TXT_INVALID    = "ملف غير صالح"
            TXT_EXPORTED   = "تم التصدير"
            TXT_RESET_DONE = "تم استرجاع الافتراضي — اضغط حفظ"
            TXT_SAVED      = "تم حفظ بنود العقد"
            TXT_SAVE_FAIL  = "فشل الحفظ"
            TXT_NEW_TITLE  = "عنوان جديد"
            TXT_NEW_BODY   = "نص المادة الجديدة..."
            TXT_BAD_NUM    = "البند"
        else:
            TXT_TITLE      = "Articles du contrat (Francais)"
            TXT_VARIABLES  = ("Variables disponibles : {name} {nid} {birth} {address} "
                              "{car} {km} {trim} {color} {gearbox} {plate} "
                              "{chassis} {price} {when} {company} {city}")
            TXT_ADD        = "Ajouter un article"
            TXT_RESET      = "Restaurer le defaut"
            TXT_EXPORT     = "Exporter un fichier"
            TXT_IMPORT     = "Importer un fichier"
            TXT_SAVE       = "Enregistrer"
            TXT_CANCEL     = "Annuler"
            TXT_DELETE     = "Supprimer"
            TXT_TITLE_HINT = "Titre de l'article"
            TXT_BODY_HINT  = "Texte de l'article"
            TXT_IMPORTED   = "Importe - cliquez sur Enregistrer"
            TXT_INVALID    = "Fichier invalide"
            TXT_EXPORTED   = "Exporte"
            TXT_RESET_DONE = "Defaut restaure - cliquez sur Enregistrer"
            TXT_SAVED      = "Articles enregistres"
            TXT_SAVE_FAIL  = "Echec de l'enregistrement"
            TXT_NEW_TITLE  = "Nouveau titre"
            TXT_NEW_BODY   = "Texte du nouvel article..."
            TXT_BAD_NUM    = "Article"

        def _txt(s):
            return self.ar(s) if L == "ar" else s

        def build_editor():
            container = MDBoxLayout(orientation="vertical", size_hint_y=None,
                                    spacing=dp(12),
                                    padding=[dp(8), dp(8), dp(8), dp(8)],
                                    adaptive_height=True)

            info = MDLabel(
                text=_txt(TXT_VARIABLES),
                size_hint_y=None, font_size="11sp",
                halign="right" if L == "ar" else "left",
                valign="middle",
                theme_text_color="Custom", text_color=(0.5, 0.5, 0.55, 1))
            info.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
            info.bind(texture_size=lambda i, ts: setattr(i, "height", ts[1] + 10))
            container.add_widget(info)

            articles_box = MDBoxLayout(orientation="vertical", size_hint_y=None,
                                       spacing=dp(10), adaptive_height=True)
            container.add_widget(articles_box)

            def refresh_list():
                articles_box.clear_widgets()
                for idx, art in enumerate(self._edited_articles):
                    card = MDCard(orientation="vertical", size_hint_y=None,
                                  adaptive_height=True, padding="10dp",
                                  spacing="8dp", radius=[12], elevation=1,
                                  md_bg_color=(0.98, 0.98, 1.0, 1))

                    head = MDBoxLayout(orientation="horizontal",
                                       size_hint_y=None, height=dp(32),
                                       spacing=dp(6))
                    n_text = f"{TXT_BAD_NUM} {idx + 1}"
                    head.add_widget(MDLabel(
                        text=_txt(n_text),
                        bold=True, font_size="13sp",
                        halign="right" if L == "ar" else "left",
                        theme_text_color="Custom",
                        text_color=(0.08, 0.45, 0.75, 1)))

                    btn_del = MDFlatButton(
                        text=_txt(TXT_DELETE),
                        text_color=(0.75, 0.22, 0.17, 1),
                        size_hint_x=None, width=dp(90))

                    def _del(_=None, i=idx):
                        del self._edited_articles[i]
                        refresh_list()
                    btn_del.bind(on_release=_del)
                    head.add_widget(btn_del)
                    card.add_widget(head)

                    title_tf = ArabicField(
                        mode="rectangle", font_size="14sp",
                        hint_text=_txt(TXT_TITLE_HINT),
                        size_hint_y=None, height=dp(52))
                    set_field_val(title_tf, art.get("title", ""))

                    body_tf = ArabicField(
                        mode="rectangle", font_size="13sp", multiline=True,
                        hint_text=_txt(TXT_BODY_HINT),
                        size_hint_y=None, height=dp(180))
                    set_field_val(body_tf, art.get("body", ""))

                    def _sync_title(instance, _value, i=idx, tf=title_tf):
                        if 0 <= i < len(self._edited_articles):
                            self._edited_articles[i]["title"] = field_val(tf)

                    def _sync_body(instance, _value, i=idx, tf=body_tf):
                        if 0 <= i < len(self._edited_articles):
                            self._edited_articles[i]["body"] = field_val(tf)

                    title_tf.bind(text=_sync_title)
                    body_tf.bind(text=_sync_body)

                    card.add_widget(title_tf)
                    card.add_widget(body_tf)
                    articles_box.add_widget(card)

            def add_article(_=None):
                n = len(self._edited_articles) + 1
                if L == "ar":
                    self._edited_articles.append({
                        "title": f"المادة {n:02d}: {TXT_NEW_TITLE}",
                        "body": TXT_NEW_BODY
                    })
                else:
                    self._edited_articles.append({
                        "title": f"Article {n:02d} : {TXT_NEW_TITLE}",
                        "body": TXT_NEW_BODY
                    })
                refresh_list()

            def reset_all(_=None):
                self._edited_articles = [dict(a) for a in DEFAULT_ARTICLES[L]]
                refresh_list()
                self.notify(_txt(TXT_RESET_DONE))

            def export_file(_=None):
                try:
                    d = csv_dir()
                    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    path = os.path.join(d, f"articles_{L}_{ts}.json")
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(self._edited_articles, f,
                                  ensure_ascii=False, indent=2)
                    self.notify(f"{_txt(TXT_EXPORTED)}: {os.path.basename(path)}")
                except Exception as e:
                    self.notify(f"Error: {str(e)[:40]}")

            def import_file(_=None):
                def _on_pick(filepath):
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        if isinstance(data, list) and all(
                                "title" in a and "body" in a for a in data):
                            self._edited_articles = data
                            refresh_list()
                            self.notify(_txt(TXT_IMPORTED))
                        else:
                            self.notify(_txt(TXT_INVALID))
                    except Exception as e:
                        self.notify(f"Error: {str(e)[:40]}")

                from kivymd.uix.filemanager import MDFileManager
                start = ("/storage/emulated/0" if _kivy_platform == "android"
                         else os.path.expanduser("~"))
                fm = MDFileManager(
                    exit_manager=lambda *a: fm.close(),
                    select_path=lambda p: (_on_pick(p), fm.close()),
                    ext=[".json"])
                fm.show(start)

            refresh_list()

            btn_row = MDBoxLayout(orientation="horizontal", size_hint_y=None,
                                  height=dp(48), spacing=dp(8))
            btn_row.add_widget(MDRaisedButton(
                text=_txt(TXT_ADD),
                md_bg_color=(0.15, 0.55, 0.32, 1),
                on_release=add_article))
            btn_row.add_widget(MDRaisedButton(
                text=_txt(TXT_RESET),
                md_bg_color=(0.95, 0.61, 0.07, 1),
                on_release=reset_all))
            container.add_widget(btn_row)

            file_row = MDBoxLayout(orientation="horizontal", size_hint_y=None,
                                   height=dp(44), spacing=dp(8))
            file_row.add_widget(MDRaisedButton(
                text=_txt(TXT_EXPORT),
                md_bg_color=(0.55, 0.27, 0.68, 1),
                on_release=export_file))
            file_row.add_widget(MDRaisedButton(
                text=_txt(TXT_IMPORT),
                md_bg_color=(0.0, 0.55, 0.62, 1),
                on_release=import_file))
            container.add_widget(file_row)

            return container

        content = build_editor()
        sv = ScrollView(size_hint_y=None, do_scroll_x=False)
        sv.height = Window.height * 0.75
        sv.add_widget(content)
        sv.scroll_y = 1

        def save_all(_=None):
            ok = save_contract_articles(L, self._edited_articles)
            if ok:
                self.notify(_txt(TXT_SAVED))
                self.articles_dialog.dismiss()
                self.articles_dialog = None
            else:
                self.notify(_txt(TXT_SAVE_FAIL))

        self.articles_dialog = self.dlg(
            title=_txt(TXT_TITLE),
            type="custom",
            content_cls=sv,
            buttons=[
                MDFlatButton(text=_txt(TXT_CANCEL),
                             on_release=lambda x: self.articles_dialog.dismiss()),
                MDRaisedButton(text=_txt(TXT_SAVE),
                               md_bg_color=(0.08, 0.45, 0.75, 1),
                               on_release=save_all),
            ])
        self.articles_dialog.open()

    # ========== رسالة الترحيب ==========
    def show_welcome_dialog(self):
        from kivy.uix.scrollview import ScrollView
        L = self.current_lang
        if L == "ar":
            text = (
                "[size=22][b]مرحباً بك في Showroom Manager[/b][/size]\n\n"
                "تطبيق متكامل لإدارة معرض السيارات:\n\n"
                "• إدارة السيارات (متوفرة / محجوزة / مباعة)\n"
                "• إدارة الزبائن مع كامل بياناتهم\n"
                "• توليد عقود ووصولات PDF احترافية\n"
                "• لوحة إحصائيات وأرباح\n"
                "• نسخ احتياطي تلقائي\n\n"
                "[b]النسخة المجانية تشمل:[/b]\n"
                "• إضافة حتى [b]3 سيارات[/b]\n"
                "• إضافة حتى [b]3 زبائن[/b]\n"
                "• إنشاء حتى [b]3 عقود[/b]\n"
                "• جميع ميزات PDF والإحصائيات\n\n"
                "[b]للترقية إلى النسخة الكاملة:[/b]\n"
                "• سيارات وزبائن وعقود [b]بلا حدود[/b]\n"
                "• تعديل معلومات الشركة والبنك\n"
                "• جميع ألوان PDF\n"
                "• دعم فني مباشر\n"
                f"• السعر: [b]{FREE_PRICE_DZD} دج[/b] مدى الحياة\n\n"
                "من الإعدادات، اضغط ترقية الآن"
            )
        else:
            text = (
                "[size=22][b]Bienvenue dans Showroom Manager[/b][/size]\n\n"
                "Application complete de gestion de showroom :\n\n"
                "• Gestion des vehicules\n"
                "• Gestion des clients\n"
                "• Generation de contrats PDF\n"
                "• Tableau de bord & benefices\n"
                "• Sauvegarde automatique\n\n"
                "[b]Version gratuite :[/b]\n"
                "• Jusqu'a [b]3 vehicules[/b]\n"
                "• Jusqu'a [b]3 clients[/b]\n"
                "• Jusqu'a [b]3 contrats[/b]\n"
                "• Toutes les fonctions PDF\n\n"
                "[b]Version complete :[/b]\n"
                "• Illimite\n"
                "• Modifier societe & banque\n"
                "• 10 themes PDF\n"
                f"• Prix : [b]{FREE_PRICE_DZD} DA[/b]\n\n"
                "Depuis Parametres, cliquez Mettre a niveau"
            )
        sv = ScrollView(size_hint_y=None, height=dp(520), do_scroll_x=False)
        lbl = MDLabel(text=self.ar_markup(text), markup=True,
                      halign="right" if L == "ar" else "left",
                      size_hint_y=None, theme_text_color="Primary")
        lbl.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
        lbl.bind(texture_size=lambda i, ts: setattr(i, "height", ts[1]))
        sv.add_widget(lbl)

        self.welcome_dialog = self.dlg(
            title=self.trd("welcome_title"),
            type="custom",
            content_cls=sv,
            buttons=[
                MDFlatButton(text=self.trd("close"),
                             on_release=lambda x: self.welcome_dialog.dismiss()),
                MDRaisedButton(text=self.trd("upgrade_now"),
                               md_bg_color=(0.15, 0.55, 0.32, 1),
                               on_release=lambda x: (self.welcome_dialog.dismiss(),
                                                     self.show_upgrade_dialog(""))),
            ])
        self.welcome_dialog.open()

    # ========== الترقية ==========
    def show_upgrade_dialog(self, reason=""):
        if self.is_premium():
            self.notify(self.ar("التطبيق مفعّل بالفعل") if self.current_lang == "ar"
                        else "Application deja active")
            return
        L = self.current_lang
        device_id = get_device_id()

        if L == "ar":
            reason_msgs = {
                "car_limit": "وصلت للحد الأقصى (3 سيارات)",
                "client_limit": "وصلت للحد الأقصى (3 زبائن)",
                "contract_limit": "وصلت للحد الأقصى (3 عقود)",
                "company_locked": "معلومات الشركة غير قابلة للتعديل",
                "bank_locked": "معلومات البنك غير قابلة للتعديل",
                "premium_locked": self.tr("premium_locked"),
                "": "احصل على النسخة الكاملة",
            }
            features = (
                "سيارات وزبائن وعقود بلا حدود\n"
                "تعديل معلومات الشركة والشعار\n"
                "تعديل معلومات البنك\n"
                "جميع ألوان مستندات PDF\n"
                "دعم فني مباشر\n\n"
                f"السعر: {FREE_PRICE_DZD} دج مدى الحياة"
            )
            T_DEVICE = "معرّف جهازك (أرسله عند الدفع):"
            T_COPY   = "نسخ المعرّف"
            T_CODE   = "بعد الدفع، أدخل كود التفعيل:"
            T_ACT    = "تفعيل الآن"
        else:
            reason_msgs = {
                "car_limit": "Limite atteinte (3 vehicules)",
                "client_limit": "Limite atteinte (3 clients)",
                "contract_limit": "Limite atteinte (3 contrats)",
                "company_locked": "Societe non modifiable",
                "bank_locked": "Banque non modifiable",
                "premium_locked": self.tr("premium_locked"),
                "": "Obtenez la version complete",
            }
            features = (
                "Vehicules / clients / contrats illimites\n"
                "Modifier societe et logo\n"
                "Modifier infos bancaires\n"
                "10 themes PDF\n"
                "Support direct\n\n"
                f"Prix: {FREE_PRICE_DZD} DA a vie"
            )
            T_DEVICE = "ID de l'appareil (envoyez-le) :"
            T_COPY   = "Copier l'ID"
            T_CODE   = "Apres paiement, entrez le code :"
            T_ACT    = "Activer"

        reason_msg = reason_msgs.get(reason, reason_msgs[""])

        box = MDBoxLayout(orientation="vertical", size_hint_y=None,
                          spacing=dp(10),
                          padding=[dp(10), dp(8), dp(10), dp(10)],
                          adaptive_height=True)
        box.add_widget(MDLabel(
            text=self.ar(reason_msg) if L == "ar" else reason_msg,
            size_hint_y=None, height=dp(40),
            bold=True, font_size="14sp", halign="center",
            theme_text_color="Custom", text_color=(0.75, 0.22, 0.17, 1)))

        f_lbl = MDLabel(text=self.ar(features) if L == "ar" else features,
                        halign="right" if L == "ar" else "left",
                        size_hint_y=None, font_size="13sp",
                        theme_text_color="Custom",
                        text_color=(0.15, 0.15, 0.20, 1))
        f_lbl.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
        f_lbl.bind(texture_size=lambda i, ts: setattr(i, "height", ts[1] + 10))
        box.add_widget(f_lbl)

        box.add_widget(MDLabel(
            text=self.ar(T_DEVICE) if L == "ar" else T_DEVICE,
            size_hint_y=None, height=dp(24), bold=True, font_size="12sp",
            halign="right" if L == "ar" else "left",
            theme_text_color="Custom", text_color=(0.08, 0.45, 0.75, 1)))
        did_field = MDTextField(text=device_id, readonly=True,
                                mode="rectangle", font_size="14sp",
                                icon_left="identifier", halign="center")
        box.add_widget(did_field)

        def copy_did(_=None):
            try:
                Clipboard.copy(device_id)
                self.notify(self.tr("copied_ok"))
            except Exception:
                pass
        box.add_widget(MDFlatButton(
            text=self.ar(T_COPY) if L == "ar" else T_COPY,
            pos_hint={"center_x": 0.5},
            on_release=copy_did))

        def open_wa(_=None):
            try:
                from kivy.utils import platform
                from urllib.parse import quote
                msg = f"ترقية Showroom Manager. معرّف الجهاز: {device_id}"
                url = "https://wa.me/213553762791?text=" + quote(msg)
                if platform == "android":
                    from jnius import autoclass, cast
                    PythonActivity = autoclass('org.kivy.android.PythonActivity')
                    Intent = autoclass('android.content.Intent')
                    Uri = autoclass('android.net.Uri')
                    String = autoclass('java.lang.String')
                    intent = Intent(Intent.ACTION_VIEW)
                    intent.setData(Uri.parse(url))
                    try:
                        PythonActivity.mActivity.startActivity(intent)
                        self.notify("WhatsApp")
                    except Exception:
                        chooser = Intent.createChooser(intent,
                            cast('java.lang.CharSequence', String("Ouvrir")))
                        PythonActivity.mActivity.startActivity(chooser)
                else:
                    Clipboard.copy(url)
                    self.notify(self.tr("copied_ok"))
            except Exception as e:
                print("WA error:", e)
                self.notify(f"Error: {str(e)[:40]}")

        box.add_widget(MDRaisedButton(
            text="WhatsApp",
            md_bg_color=(0.15, 0.68, 0.38, 1),
            size_hint_y=None, height=dp(52),
            pos_hint={"center_x": 0.5},
            on_release=open_wa))

        box.add_widget(MDLabel(
            text=self.ar(T_CODE) if L == "ar" else T_CODE,
            size_hint_y=None, height=dp(24), bold=True, font_size="13sp",
            halign="right" if L == "ar" else "left",
            theme_text_color="Custom", text_color=(0.08, 0.45, 0.75, 1)))
        code_field = MDTextField(mode="rectangle", font_size="12sp",
                                 icon_left="key", multiline=False)
        box.add_widget(code_field)

        def paste_code(_=None):
            try:
                pasted = Clipboard.paste()
                if pasted:
                    code_field.text = pasted.strip()
            except Exception:
                pass
        box.add_widget(MDFlatButton(
            text=self.trd("paste"),
            pos_hint={"center_x": 0.5},
            on_release=paste_code))

        def on_activate(_=None):
            code = (code_field.text or "").strip()
            if not code:
                self.notify(self.tr("enter_activation"))
                return
            if check_activation(device_id, code):
                try:
                    conn = sqlite3.connect(get_db_path())
                    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('license_key', ?)", (code,))
                    conn.commit()
                    conn.close()
                except Exception:
                    pass
                self.upgrade_dialog.dismiss()
                self.upgrade_dialog = None
                self.refresh_premium_ui()
                self.notify("Active!")
                self.refresh_app_title()
            else:
                self.notify(self.tr("activation_bad"))

        box.add_widget(MDRaisedButton(
            text=self.ar(T_ACT) if L == "ar" else T_ACT,
            md_bg_color=(0.15, 0.55, 0.32, 1),
            size_hint_y=None, height=dp(48),
            pos_hint={"center_x": 0.5},
            on_release=on_activate))

        self.upgrade_dialog = self.dlg(
            title=self.trd("upgrade_title"),
            type="custom",
            content_cls=self.wrap_dialog(box),
            buttons=[MDFlatButton(text=self.trd("close"),
                                  on_release=lambda x: self.upgrade_dialog.dismiss())])
        self.upgrade_dialog.open()

    # ========== النسخ الاحتياطي ==========
    def backup_db(self, prefix="backup"):
        try:
            path = os.path.join(db_dir(),
                                datetime.datetime.now().strftime(prefix + "_%Y%m%d_%H%M%S_%f.db"))
            src = sqlite3.connect(get_db_path())
            dst = sqlite3.connect(path)
            src.backup(dst)
            dst.close()
            src.close()
            msg = (self.ar(f"تم الحفظ: {os.path.basename(path)}")
                   if self.current_lang == "ar"
                   else f"Sauvegarde: {os.path.basename(path)}")
            self.notify(msg)
            return path
        except Exception as e:
            self.notify(f"Error: {str(e)[:40]}")
            return None

    def share_backup(self):
        try:
            path = self.backup_db("share")
            if not path:
                return
            from kivy.utils import platform
            if platform == "android":
                from jnius import autoclass, cast
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                Intent = autoclass('android.content.Intent')
                Uri = autoclass('android.net.Uri')
                File = autoclass('java.io.File')
                String = autoclass('java.lang.String')
                activity = PythonActivity.mActivity
                FileProvider = autoclass('androidx.core.content.FileProvider')
                uri = FileProvider.getUriForFile(
                    activity, activity.getPackageName() + ".fileprovider",
                    File(path))
                intent = Intent(Intent.ACTION_SEND)
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                intent.setType("application/octet-stream")
                intent.putExtra(Intent.EXTRA_STREAM,
                                cast('android.os.Parcelable', uri))
                intent.putExtra(Intent.EXTRA_SUBJECT, cast(
                    'java.lang.CharSequence',
                    String("Showroom Manager - Backup")))
                chooser = Intent.createChooser(intent,
                    cast('java.lang.CharSequence',
                         String(self.tr("backup_share_title"))))
                activity.startActivity(chooser)
            else:
                self.notify(f"OK: {path}")
        except Exception as e:
            print("share_backup error:", e)
            self.notify(f"Error: {str(e)[:40]}")

    def auto_backup(self):
        try:
            last = self.get_setting("last_auto_backup")
            now = datetime.datetime.now()
            should = False
            if not last:
                should = True
            else:
                try:
                    if (now - datetime.datetime.fromisoformat(last)).days >= 1:
                        should = True
                except Exception:
                    should = True
            if should:
                path = self.backup_db("auto")
                if path:
                    try:
                        conn = sqlite3.connect(get_db_path())
                        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                                     ("last_auto_backup", now.isoformat()))
                        conn.commit()
                        conn.close()
                    except Exception:
                        pass
                    self.refresh_last_backup_text()
        except Exception as e:
            print("Auto backup:", e)

    def cleanup_old_backups(self, keep=10):
        try:
            d = db_dir()
            files = []
            for f in os.listdir(d):
                if f.endswith(".db") and ("auto_" in f or "backup_" in f):
                    p = os.path.join(d, f)
                    files.append((os.path.getmtime(p), p))
            files.sort(reverse=True)
            for _, p in files[keep:]:
                try: os.remove(p)
                except Exception: pass
        except Exception:
            pass

    # ========== تصدير CSV ==========
    def export_csv(self, table_name):
        import csv
        try:
            if table_name == "cars":
                query = """SELECT id, name, name_fr, mileage, price, status,
                                  trim, color, gearbox, plate, chassis, profit_margin
                           FROM cars ORDER BY id"""
                headers = ["ID", "Name", "Name_FR", "Mileage", "Price", "Status",
                           "Trim", "Color", "Gearbox", "Plate", "Chassis", "Profit"]
            elif table_name == "clients":
                query = """SELECT id, full_name, full_name_fr, national_id,
                                  birth_info, address, address_fr
                           FROM clients ORDER BY id"""
                headers = ["ID", "Full_Name", "Full_Name_FR", "NID",
                           "Birth", "Address", "Address_FR"]
            elif table_name == "contracts":
                query = """SELECT contracts.id, cars.name, clients.full_name,
                                  contract_price, paid_amount, remaining_amount, date
                           FROM contracts
                           JOIN cars ON contracts.car_id = cars.id
                           JOIN clients ON contracts.client_id = clients.id
                           ORDER BY contracts.id"""
                headers = ["ID", "Car", "Client", "Price", "Paid", "Remaining", "Date"]
            else:
                return None
            conn = sqlite3.connect(get_db_path())
            rows = conn.execute(query).fetchall()
            conn.close()
            d = csv_dir()
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{table_name}_{ts}.csv"
            path = os.path.join(d, filename)
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(headers)
                w.writerows(rows)
            self.notify(f"OK: {filename}")
            return path
        except Exception as e:
            self.notify(f"Error: {str(e)[:40]}")
            return None

    # ========== السيارات ==========
    def _render_cars(self, query=""):
        self.root.ids.cars_list.clear_widgets()
        q = clean_text(query).strip().lower()
        conn = sqlite3.connect(get_db_path())
        c = conn.cursor()
        c.execute("SELECT id, name, mileage, price, status, trim, color, gearbox, plate, chassis, name_fr FROM cars ORDER BY status ASC, id DESC")
        cars = c.fetchall()
        conn.close()
        styles = {1: (self.tr("available"), "#27AE60"),
                  2: (self.tr("reserved"), "#F39C12"),
                  3: (self.tr("sold"), "#C0392B")}
        counts = {1: 0, 2: 0, 3: 0}
        for car_id, name, mileage, price, status, trim, color, gearbox, plate, chassis, name_fr in cars:
            try: status = int(status)
            except Exception: status = 3
            if status not in styles: status = 3
            counts[status] += 1
            if q:
                hay = " ".join(str(x or "") for x in (name, name_fr, plate, chassis, trim, color)).lower()
                if q not in hay:
                    continue
            label, status_color = styles[status]
            v_trim = f"{self.tr('version_prefix')}{trim}" if trim else ""
            v_color = f"{self.tr('color_prefix')}{loc_color(color, self.current_lang)}" if color else ""
            v_gearbox = f"{self.tr('gearbox_prefix')}{loc_gearbox(gearbox, self.current_lang)}" if gearbox else ""
            v_plate = f"{self.tr('plate_prefix')}{plate}" if plate else ""
            v_chassis = f"{self.tr('chassis_prefix')}{chassis}" if chassis else ""
            item = CarCard(
                car_id=car_id,
                title=self.ar(pick_name(name, name_fr, self.current_lang)),
                subtitle=self.ar(f"{mileage} {self.tr('km_unit')}  |  {loc_amount(price, self.current_lang)}"),
                details=self.ar("  |  ".join(v for v in (v_trim, v_color, v_gearbox) if v)),
                details2=self.ar("  |  ".join(v for v in (v_plate, v_chassis) if v)),
                status_text=self.ar(label),
                accent=get_color_from_hex(status_color),
            )
            item.bind(on_release=self.on_car_select)
            self.root.ids.cars_list.add_widget(item)
        ids = self.root.ids
        ids.stat_available.value = str(counts[1])
        ids.stat_reserved.value = str(counts[2])
        ids.stat_sold.value = str(counts[3])

    def load_cars(self):
        self._render_cars("")

    def search_cars(self, query):
        self._render_cars(query)

    def show_add_car_dialog(self):
        if not self.is_premium() and self.car_count() >= FREE_LIMIT_CARS:
            self.show_upgrade_dialog("car_limit")
            return
        self.current_car_id = None
        content = CarDialogContent()
        self.style_form(content, "add_car_title", "car")
        self.car_dialog = self.dlg(title="", type="custom",
                                   content_cls=self.wrap_dialog(content),
                                   buttons=[self.btn_cancel(lambda x: self.car_dialog.dismiss()),
                                            self.btn_save("save", lambda x, c=content: self.save_car(c))])
        self.car_dialog.open()

    def save_car(self, content):
        try:
            name = clean_text(field_val(content.ids.name_input)).strip()
            name_fr = clean_text(field_val(content.ids.name_fr_input)).strip()
            mileage = clean_text(field_val(content.ids.mileage_input)).strip()
            price = clean_text(field_val(content.ids.price_input)).strip()
            trim = clean_text(field_val(content.ids.trim_input)).strip()
            color = clean_text(field_val(content.ids.color_input)).strip()
            plate = clean_text(field_val(content.ids.plate_input)).strip()
            chassis = clean_text(field_val(content.ids.chassis_input)).strip()
            profit = clean_text(field_val(content.ids.profit_input)).strip()
            if re.fullmatch(r"[\d\s.,]+", profit or "") and profit:
                profit = f"{profit} مليون"
            gb_map = {ar(self.tr("automatic")): "أوتوماتيك",
                      ar(self.tr("manual")): "يدوي",
                      "أوتوماتيك": "أوتوماتيك", "يدوي": "يدوي"}
            gearbox = gb_map.get(content.ids.gearbox_spinner.text, "")
            status = self._spinner_status_code(content.ids.status_spinner)
            name = name or name_fr
            if not name or not price:
                self.notify(self.tr("fill_car_price_err"))
                return
            conn = sqlite3.connect(get_db_path())
            c = conn.cursor()
            if self.current_car_id:
                c.execute("UPDATE cars SET name=?, mileage=?, price=?, status=?, trim=?, color=?, gearbox=?, plate=?, chassis=?, name_fr=?, profit_margin=? WHERE id=?",
                          (name, mileage, price, status, trim, color, gearbox, plate, chassis, name_fr, profit, self.current_car_id))
                self.notify(self.tr("updated_car_success"))
            else:
                c.execute("INSERT INTO cars (name, mileage, price, status, trim, color, gearbox, plate, chassis, name_fr, profit_margin) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (name, mileage, price, status, trim, color, gearbox, plate, chassis, name_fr, profit))
                self.notify(self.tr("saved_car_success"))
            conn.commit()
            conn.close()
            self.car_dialog.dismiss()
            self.car_dialog = None
            self.load_cars()
            self.refresh_premium_ui()
        except Exception as e:
            print("save_car error:", e)
            self.notify(self.tr("save_error"))

    def tiles_dialog(self, title, items, attr):
        from kivy.uix.gridlayout import GridLayout
        tiles = []
        for label, icon, rgb, cb in items:
            tiles.append(ActionTile(label=self.ar(label), icon=icon,
                                    tint=[rgb[0], rgb[1], rgb[2], 1],
                                    bg=[rgb[0], rgb[1], rgb[2], 0.12],
                                    on_release=lambda x, f=cb: f()))
        rows = (len(tiles) + 1) // 2
        grid = GridLayout(cols=2, spacing=dp(10), size_hint_y=None,
                          height=rows * dp(88) + (rows - 1) * dp(10))
        for i in range(0, len(tiles), 2):
            for t in reversed(tiles[i:i + 2]):
                grid.add_widget(t)
        dialog = self.dlg(title=title, type="custom", content_cls=self.wrap_dialog(grid))
        setattr(self, attr, dialog)
        dialog.open()

    def on_car_select(self, item):
        self.current_car_id = item.car_id
        is_prem = self.is_premium()
        lock_cb = lambda x: self.show_upgrade_dialog("premium_locked")
        self.tiles_dialog(item.title, [
            (self.tr("reserve_contract"), "file-sign", (0.15, 0.55, 0.32), self.reserve_car),
            (self.tr("edit"), "pencil-outline", (0.08, 0.45, 0.75), self.show_edit_car_dialog if is_prem else lock_cb),
            (self.tr("delete"), "delete-outline", (0.75, 0.22, 0.17), self.delete_car if is_prem else lock_cb),
            (self.tr("close"), "close-circle-outline", (0.45, 0.45, 0.5), lambda: self.car_action_dialog.dismiss()),
        ], "car_action_dialog")

    def reserve_car(self):
        try:
            conn = sqlite3.connect(get_db_path())
            row = conn.execute("SELECT status FROM cars WHERE id=?", (self.current_car_id,)).fetchone()
            conn.close()
        except Exception:
            row = None
        self.car_action_dialog.dismiss()
        if row and row[0] == 3:
            self.notify(self.tr("car_sold_err"))
            return
        self.show_add_contract_dialog(preselect_car_id=self.current_car_id)

    def show_edit_car_dialog(self):
        self.car_action_dialog.dismiss()
        content = CarDialogContent()
        conn = sqlite3.connect(get_db_path())
        c = conn.cursor()
        c.execute("SELECT name, mileage, price, status, trim, color, gearbox, plate, chassis, name_fr, profit_margin FROM cars WHERE id=?", (self.current_car_id,))
        car = c.fetchone()
        conn.close()
        if car:
            set_field_val(content.ids.name_input, car[0] or "")
            set_field_val(content.ids.mileage_input, car[1] or "")
            set_field_val(content.ids.price_input, loc_amount(car[2], self.current_lang))
            set_field_val(content.ids.name_fr_input, car[9] or "")
            set_field_val(content.ids.trim_input, car[4] or "")
            set_field_val(content.ids.color_input, car[5] or "")
            set_field_val(content.ids.plate_input, car[7] or "")
            set_field_val(content.ids.chassis_input, car[8] or "")
            set_field_val(content.ids.profit_input,
                          re.sub(r"(?i)\s*(مليون|millions?)\b", "", str(car[10] or "")).strip())
            if car[6]:
                content.ids.gearbox_spinner.text = ar(self.tr("automatic")) if car[6] == "أوتوماتيك" else ar(self.tr("manual"))
            if car[3] == 1:
                content.ids.status_spinner.text = ar(self.tr("available"))
            elif car[3] == 2:
                content.ids.status_spinner.text = ar(self.tr("reserved"))
            else:
                content.ids.status_spinner.text = ar(self.tr("sold"))
        self.style_form(content, "edit_car_title", "car-cog")
        self.car_dialog = self.dlg(title="", type="custom",
                                   content_cls=self.wrap_dialog(content),
                                   buttons=[self.btn_cancel(lambda x: self.car_dialog.dismiss()),
                                            self.btn_save("save_changes", lambda x, c=content: self.save_car(c))])
        self.car_dialog.open()

    def delete_car(self):
        conn = sqlite3.connect(get_db_path())
        c = conn.cursor()
        c.execute("DELETE FROM cars WHERE id=?", (self.current_car_id,))
        conn.commit()
        conn.close()
        self.car_action_dialog.dismiss()
        self.load_cars()
        self.refresh_premium_ui()
        self.notify(self.tr("car_deleted"))

    # ========== الزبائن ==========
    def _render_clients(self, query=""):
        self.root.ids.clients_list.clear_widgets()
        q = clean_text(query).strip().lower()
        conn = sqlite3.connect(get_db_path())
        c = conn.cursor()
        c.execute("SELECT id, full_name, national_id, full_name_fr FROM clients ORDER BY id DESC")
        clients = c.fetchall()
        conn.close()
        for client_id, name, nid, name_fr in clients:
            if q:
                hay = " ".join(str(x or "") for x in (name, name_fr, nid)).lower()
                if q not in hay: continue
            details = f"{self.tr('client_id_num')}{nid}" if nid else self.tr("no_id")
            item = ClientCard(client_id=client_id,
                              title=self.ar(pick_name(name, name_fr, self.current_lang)),
                              subtitle=self.ar(details))
            item.bind(on_release=self.on_client_select)
            self.root.ids.clients_list.add_widget(item)

    def load_clients(self):
        self._render_clients("")

    def search_clients(self, query):
        self._render_clients(query)

    def show_add_client_dialog(self):
        if not self.is_premium() and self.client_count() >= FREE_LIMIT_CLIENTS:
            self.show_upgrade_dialog("client_limit")
            return
        self.current_client_id = None
        content = ClientDialogContent()
        self.style_form(content, "add_client_title", "account-plus")
        self.client_dialog = self.dlg(title="", type="custom",
                                      content_cls=self.wrap_dialog(content),
                                      buttons=[self.btn_cancel(lambda x: self.client_dialog.dismiss()),
                                               self.btn_save("save", lambda x, c=content: self.save_client(c))])
        self.client_dialog.open()

    def save_client(self, content):
        try:
            name = clean_text(field_val(content.ids.name_input)).strip()
            name_fr = clean_text(field_val(content.ids.name_fr_input)).strip()
            nid = clean_text(field_val(content.ids.nid_input)).strip()
            birth = clean_text(field_val(content.ids.birth_input)).strip()
            address = clean_text(field_val(content.ids.address_input)).strip()
            address_fr = clean_text(field_val(content.ids.address_fr_input)).strip()
            name = name or name_fr
            if not name:
                self.notify(self.tr("fill_client_err"))
                return
            conn = sqlite3.connect(get_db_path())
            c = conn.cursor()
            if self.current_client_id:
                c.execute("UPDATE clients SET full_name=?, national_id=?, birth_info=?, address=?, full_name_fr=?, address_fr=? WHERE id=?",
                          (name, nid, birth, address, name_fr, address_fr, self.current_client_id))
                self.notify(self.tr("updated_client_success"))
            else:
                c.execute("INSERT INTO clients (full_name, national_id, birth_info, address, full_name_fr, address_fr) VALUES (?, ?, ?, ?, ?, ?)",
                          (name, nid, birth, address, name_fr, address_fr))
                self.notify(self.tr("saved_client_success"))
            conn.commit()
            conn.close()
            self.client_dialog.dismiss()
            self.client_dialog = None
            self.load_clients()
        except Exception as e:
            print("save_client error:", e)
            self.notify(self.tr("save_client_error"))

    def on_client_select(self, item):
        self.current_client_id = item.client_id
        is_prem = self.is_premium()
        lock_cb = lambda x: self.show_upgrade_dialog("premium_locked")
        self.client_action_dialog = self.dlg(
            title=self.trd("client_options"), text=item.title,
            buttons=[
                MDFlatButton(text=self.trd("client_history"), on_release=lambda x: self.show_client_history()),
                MDFlatButton(text=self.trd("edit"), on_release=self.show_edit_client_dialog if is_prem else lock_cb),
                MDFlatButton(text=self.trd("delete"), text_color=(1, 0, 0, 1), on_release=self.delete_client if is_prem else lock_cb),
                MDFlatButton(text=self.trd("cancel"), on_release=lambda x: self.client_action_dialog.dismiss()),
            ],
        )
        self.client_action_dialog.open()

    def show_edit_client_dialog(self):
        self.client_action_dialog.dismiss()
        content = ClientDialogContent()
        conn = sqlite3.connect(get_db_path())
        c = conn.cursor()
        c.execute("SELECT full_name, national_id, birth_info, address, full_name_fr, address_fr FROM clients WHERE id=?", (self.current_client_id,))
        client = c.fetchone()
        conn.close()
        if client:
            set_field_val(content.ids.name_input, client[0] or "")
            set_field_val(content.ids.name_fr_input, client[4] or "")
            set_field_val(content.ids.nid_input, client[1] or "")
            set_field_val(content.ids.birth_input, client[2] or "")
            set_field_val(content.ids.address_input, client[3] or "")
            set_field_val(content.ids.address_fr_input, client[5] or "")
        self.style_form(content, "edit_client_title", "account-edit")
        self.client_dialog = self.dlg(title="", type="custom",
                                      content_cls=self.wrap_dialog(content),
                                      buttons=[self.btn_cancel(lambda x: self.client_dialog.dismiss()),
                                               self.btn_save("save_changes", lambda x, c=content: self.save_client(c))])
        self.client_dialog.open()

    def delete_client(self):
        conn = sqlite3.connect(get_db_path())
        c = conn.cursor()
        c.execute("DELETE FROM clients WHERE id=?", (self.current_client_id,))
        conn.commit()
        conn.close()
        self.client_action_dialog.dismiss()
        self.load_clients()
        self.notify(self.tr("client_deleted"))

    def show_client_history(self):
        self.client_action_dialog.dismiss()
        from kivy.uix.scrollview import ScrollView
        conn = sqlite3.connect(get_db_path())
        c = conn.cursor()
        c.execute("SELECT full_name, full_name_fr, national_id, birth_info, address, address_fr FROM clients WHERE id=?",
                  (self.current_client_id,))
        client = c.fetchone()
        if not client:
            conn.close()
            return
        L = self.current_lang
        name = pick_name(client[0], client[1], L)
        nid = client[2] or "-"
        birth = client[3] or "-"
        address = pick_name(client[4], client[5], L) or "-"
        c.execute('''SELECT contracts.id, contracts.date, contracts.contract_price,
                            contracts.paid_amount, contracts.remaining_amount,
                            cars.name, cars.name_fr
                     FROM contracts JOIN cars ON contracts.car_id = cars.id
                     WHERE contracts.client_id=? ORDER BY contracts.id DESC''',
                  (self.current_client_id,))
        contracts = c.fetchall()
        conn.close()
        total_paid = 0
        total_remaining = 0
        for row in contracts:
            try:
                total_paid += int(''.join(filter(str.isdigit, str(row[3] or "0"))))
                total_remaining += int(''.join(filter(str.isdigit, str(row[4] or "0"))))
            except Exception:
                pass

        def fmt(n):
            return f"{int(n):,}".replace(",", " ")

        unit = self.tr("million")
        if L == "ar":
            lines = [f"[size=17][b]{name}[/b][/size]",
                     f"رقم التعريف: {nid}",
                     f"الميلاد: {birth}",
                     f"العنوان: {address}", "",
                     f"[b]العقود ({len(contracts)})[/b]"]
        else:
            lines = [f"[size=17][b]{name}[/b][/size]",
                     f"NIN : {nid}",
                     f"Naissance : {birth}",
                     f"Adresse : {address}", "",
                     f"[b]Contrats ({len(contracts)})[/b]"]
        for cid, date, price, paid, remaining, car, car_fr in contracts:
            cno = contract_number(cid, date)
            car_name = pick_name(car, car_fr, L)
            lines.append(f"\n• [b]{cno}[/b]\n  {car_name}\n  {loc_amount(price, L)} | {loc_amount(paid or '0', L)}")
        if not contracts:
            lines.append("  -")
        lines.append("")
        lines.append(f"[b]{self.tr('price_label')}{fmt(total_paid)} {unit}[/b]")
        lines.append(f"[b]{self.tr('remaining_label')}{fmt(total_remaining)} {unit}[/b]")
        text = "\n".join(lines)
        sv = ScrollView(size_hint_y=None, height=dp(480), do_scroll_x=False)
        lbl = MDLabel(text=self.ar_markup(text), markup=True,
                      halign="right" if L == "ar" else "left",
                      size_hint_y=None, theme_text_color="Primary")
        lbl.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
        lbl.bind(texture_size=lambda i, ts: setattr(i, "height", ts[1]))
        sv.add_widget(lbl)
        self.client_history_dialog = self.dlg(
            title=self.trd("client_history"), type="custom", content_cls=sv,
            buttons=[MDFlatButton(text=self.trd("close"),
                                  on_release=lambda x: self.client_history_dialog.dismiss())])
        self.client_history_dialog.open()

    # ========== العقود ==========
    def _render_contracts(self, query=""):
        self.root.ids.contracts_list.clear_widgets()
        q = clean_text(query).strip().lower()
        conn = sqlite3.connect(get_db_path())
        c = conn.cursor()
        c.execute('''SELECT contracts.id, cars.name, clients.full_name,
                            contracts.contract_price, contracts.remaining_amount,
                            cars.name_fr, clients.full_name_fr, cars.plate, clients.national_id
                     FROM contracts JOIN cars ON contracts.car_id = cars.id
                     JOIN clients ON contracts.client_id = clients.id
                     ORDER BY contracts.id DESC''')
        contracts = c.fetchall()
        conn.close()
        L = self.current_lang
        for cid, car_name, client_name, price, remaining, car_fr, client_fr, plate, nid in contracts:
            if q:
                hay = " ".join(str(x or "") for x in (car_name, car_fr, client_name, client_fr, plate, nid, cid)).lower()
                if q not in hay: continue
            item = ContractCard(
                contract_id=cid,
                title=self.ar(pick_name(client_name, client_fr, L)),
                subtitle=self.ar(pick_name(car_name, car_fr, L)),
                remaining=self.ar(f"{self.tr('price_label')}{loc_amount(price or '0', L)}{self.tr('remaining_label')}{loc_amount(remaining or '0', L)}"),
            )
            item.bind(on_release=self.on_contract_select)
            self.root.ids.contracts_list.add_widget(item)

    def load_contracts(self):
        self._render_contracts("")

    def search_contracts(self, query):
        self._render_contracts(query)

    def show_add_contract_dialog(self, preselect_car_id=None):
        if not self.contract_edit_id and not self.is_premium() and self.contract_count() >= FREE_LIMIT_CONTRACTS:
            self.show_upgrade_dialog("contract_limit")
            return
        self.contract_edit_id = None
        content = ContractDialogContent()
        self.active_contract_content = content
        conn = sqlite3.connect(get_db_path())
        c = conn.cursor()
        c.execute("SELECT id, name, price, name_fr, profit_margin FROM cars WHERE status=1 OR id=?", (preselect_car_id or -1,))
        cars_data = c.fetchall()
        c.execute("SELECT id, full_name, full_name_fr FROM clients")
        clients_data = c.fetchall()
        conn.close()
        L = self.current_lang
        self.style_form(content, "add_contract_title", "file-sign")
        content.car_dict = {pick_name(n, nfr, L): cid for cid, n, price, nfr, pm in cars_data}
        content.car_prices = {pick_name(n, nfr, L): price for cid, n, price, nfr, pm in cars_data}
        content.car_margins = {pick_name(n, nfr, L): (pm or "") for cid, n, price, nfr, pm in cars_data}
        content.client_dict = {pick_name(n, nfr, L): cid for cid, n, nfr in clients_data}
        content.ids.car_spinner.values = [self.ar(n) for n in content.car_dict.keys()] if content.car_dict else [self.trd("no_cars_avail")]
        content.ids.client_spinner.values = [self.ar(n) for n in content.client_dict.keys()] if content.client_dict else [self.trd("no_clients_avail")]
        if preselect_car_id:
            for n, i in content.car_dict.items():
                if i == preselect_car_id:
                    content.ids.car_spinner.text = self.ar(n)
                    pm = content.car_margins.get(n, "")
                    if pm:
                        set_field_val(content.ids.profit_input,
                                      re.sub(r"(?i)\s*(مليون|millions?)\b", "", str(pm)).strip())
        self.contract_dialog = self.dlg(title="", type="custom",
                                        content_cls=self.wrap_dialog(content))
        self.contract_dialog.open()

    def show_edit_contract_dialog(self):
        self.contract_action_dialog.dismiss()
        cid = self.current_contract_id
        conn = sqlite3.connect(get_db_path())
        c = conn.cursor()
        c.execute("SELECT car_id, client_id, contract_price, paid_amount FROM contracts WHERE id=?", (cid,))
        row = c.fetchone()
        if not row:
            conn.close()
            return
        cur_car, cur_client, price, paid = row
        c.execute("SELECT id, name, price, name_fr, profit_margin FROM cars WHERE status=1 OR id=?", (cur_car,))
        cars_data = c.fetchall()
        c.execute("SELECT id, full_name, full_name_fr FROM clients")
        clients_data = c.fetchall()
        conn.close()
        L = self.current_lang
        self.contract_edit_id = cid
        content = ContractDialogContent()
        self.active_contract_content = content
        self.style_form(content, "edit_contract_title", "file-document-edit-outline")
        content.car_dict = {pick_name(n, nfr, L): i for i, n, _, nfr, pm in cars_data}
        content.car_prices = {pick_name(n, nfr, L): pr for _, n, pr, nfr, pm in cars_data}
        content.car_margins = {pick_name(n, nfr, L): (pm or "") for _, n, pr, nfr, pm in cars_data}
        content.client_dict = {pick_name(n, nfr, L): i for i, n, nfr in clients_data}
        content.ids.car_spinner.values = [self.ar(n) for n in content.car_dict]
        content.ids.client_spinner.values = [self.ar(n) for n in content.client_dict]
        for n, i in content.car_dict.items():
            if i == cur_car:
                content.ids.car_spinner.text = self.ar(n)
                pm = content.car_margins.get(n, "")
                if pm:
                    set_field_val(content.ids.profit_input,
                                  re.sub(r"(?i)\s*(مليون|millions?)\b", "", str(pm)).strip())
        for n, i in content.client_dict.items():
            if i == cur_client:
                content.ids.client_spinner.text = self.ar(n)
        set_field_val(content.ids.price_input, loc_amount(price or "", L))
        set_field_val(content.ids.paid_input, re.sub(r"(?i)\s*(مليون|millions?)\b", "", str(paid or "")).strip())
        self.contract_dialog = self.dlg(title="", type="custom",
                                        content_cls=self.wrap_dialog(content))
        self.contract_dialog.open()

    def on_car_spinner_select(self, text):
        if not self.active_contract_content:
            return
        content = self.active_contract_content
        for name in content.car_prices:
            if self.ar(name) == text:
                set_field_val(content.ids.price_input,
                              loc_amount(content.car_prices[name], self.current_lang))
                pm = content.car_margins.get(name, "")
                if pm:
                    set_field_val(content.ids.profit_input,
                                  re.sub(r"(?i)\s*(مليون|millions?)\b", "", str(pm)).strip())
                break

    def calculate_remaining(self, paid_text):
        if not self.active_contract_content:
            return
        try:
            content = self.active_contract_content
            total_str = clean_text(field_val(content.ids.price_input)).strip()
            total = float(''.join(filter(str.isdigit, total_str))) if total_str else 0.0
            paid = float(''.join(filter(str.isdigit, paid_text))) if paid_text else 0.0
            rem_val = int(max(total - paid, 0))
            content.remaining_raw = f"{rem_val} مليون"
            set_field_val(content.ids.remaining_input,
                          loc_amount(content.remaining_raw, self.current_lang))
        except Exception:
            pass

    def save_contract(self, content):
        try:
            car_ar = content.ids.car_spinner.text
            client_ar = content.ids.client_spinner.text
            price = clean_text(field_val(content.ids.price_input)).strip()
            paid_raw = clean_text(field_val(content.ids.paid_input)).strip()
            profit_input = clean_text(field_val(content.ids.profit_input)).strip()
            remaining = getattr(content, "remaining_raw", None) or ""
            if not remaining:
                try:
                    tn = float(''.join(filter(str.isdigit, price))) if price else 0.0
                    pn = float(''.join(filter(str.isdigit, paid_raw))) if paid_raw else 0.0
                    rem = int(tn - pn)
                    remaining = f"{rem if rem >= 0 else 0} مليون"
                except Exception:
                    remaining = ""
            if self._is_opt(car_ar, "select_car") or self._is_opt(client_ar, "select_client") or not price:
                self.notify(self.tr("fill_contract_err"))
                return
            paid = f"{paid_raw} مليون" if re.fullmatch(r"[\d\s.,]+", paid_raw or "") and paid_raw else paid_raw
            car_id = None
            for name, cid in content.car_dict.items():
                if self.ar(name) == car_ar:
                    car_id = cid
                    break
            client_id = None
            for name, cid in content.client_dict.items():
                if self.ar(name) == client_ar:
                    client_id = cid
                    break
            if not car_id or not client_id:
                self.notify(self.tr("data_id_error"))
                return
            profit_stored = ""
            if profit_input:
                if re.fullmatch(r"[\d\s.,]+", profit_input):
                    profit_stored = f"{profit_input} مليون"
                else:
                    profit_stored = profit_input
            conn = sqlite3.connect(get_db_path())
            c = conn.cursor()
            if self.contract_edit_id:
                contract_id = self.contract_edit_id
                c.execute("SELECT car_id FROM contracts WHERE id=?", (contract_id,))
                old_car = c.fetchone()[0]
                c.execute("UPDATE contracts SET car_id=?, client_id=?, contract_price=?, paid_amount=?, remaining_amount=? WHERE id=?",
                          (car_id, client_id, price, paid, remaining, contract_id))
                if old_car != car_id:
                    c.execute("UPDATE cars SET status=1 WHERE id=?", (old_car,))
                c.execute("UPDATE cars SET status=3 WHERE id=?", (car_id,))
                self.contract_edit_id = None
            else:
                c.execute("INSERT INTO contracts (car_id, client_id, contract_price, paid_amount, remaining_amount, date) VALUES (?, ?, ?, ?, ?, datetime('now','localtime'))",
                          (car_id, client_id, price, paid, remaining))
                contract_id = c.lastrowid
                c.execute("UPDATE cars SET status=3 WHERE id=?", (car_id,))
            if profit_stored:
                c.execute("UPDATE cars SET profit_margin=? WHERE id=?", (profit_stored, car_id))
            conn.commit()
            conn.close()
            self.contract_dialog.dismiss()
            self.contract_dialog = None
            self.load_contracts()
            self.load_cars()
            self.generate_contract_pdf(contract_id)
            self.notify(self.tr("contract_pdf_success"))
        except Exception as e:
            print("save_contract error:", e)
            self.notify(self.tr("save_error"))

    def on_contract_select(self, item):
        self.current_contract_id = item.contract_id
        is_prem = self.is_premium()
        lock_cb = lambda x: self.show_upgrade_dialog("premium_locked")
        self.tiles_dialog(item.title, [
            (self.tr("edit_contract"), "file-edit-outline", (0.08, 0.45, 0.75), self.show_edit_contract_dialog if is_prem else lock_cb),
            (self.tr("order_receipt"), "truck-delivery-outline", (0.0, 0.55, 0.62), self.start_order_receipt),
            (self.tr("payment_order"), "bank-transfer", (0.55, 0.27, 0.68), self.ask_payment_amount),
            (self.tr("download_pdf"), "file-pdf-box", (0.15, 0.55, 0.32), self.reprint_pdf),
            (self.tr("cancel_contract"), "file-cancel-outline", (0.75, 0.22, 0.17), self.delete_contract if is_prem else lock_cb),
            (self.tr("close"), "close-circle-outline", (0.45, 0.45, 0.5), lambda: self.contract_action_dialog.dismiss()),
        ], "contract_action_dialog")

    def open_file_manager(self, mode, ext, hint):
        self.fm_mode = mode
        from kivy.utils import platform
        start = os.path.expanduser("~")
        if platform == "android":
            start = "/storage/emulated/0"
        from kivymd.uix.filemanager import MDFileManager
        self.file_manager = MDFileManager(
            exit_manager=self.close_file_manager,
            select_path=self.on_doc_selected,
            ext=ext,
        )
        self.notify(hint)
        self.file_manager.show(start)

    def start_order_receipt(self):
        self.contract_action_dialog.dismiss()
        self.order_contract_id = self.current_contract_id
        self.open_file_manager("order", [".pdf", ".jpg", ".jpeg", ".png"],
                               self.tr("pick_id_file"))

    def close_file_manager(self, *args):
        try: self.file_manager.close()
        except Exception: pass

    def on_doc_selected(self, path):
        if not os.path.isfile(path):
            return
        self.close_file_manager()
        if getattr(self, "fm_mode", "") == "restore":
            self.confirm_restore(path)
            return
        try:
            self.generate_order_pdf(self.order_contract_id, path)
            self.notify(self.tr("order_pdf_success"))
        except Exception as e:
            print("order_pdf error:", e)
            self.notify(self.tr("save_error"))

    # ========== الإعدادات ==========
    def get_setting(self, key):
        try:
            conn = sqlite3.connect(get_db_path())
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            conn.close()
            return row[0] if row and row[0] else ""
        except Exception:
            return ""

    def load_settings(self):
        try:
            ids = self.root.ids
            saved_lang = self.get_setting("lang") or "ar"
            self.current_lang = saved_lang
            if "lang_selector" in ids:
                try:
                    ids.lang_selector.active_lang = saved_lang
                except Exception:
                    pass
            theme_name = self.get_setting("pdf_color") or "blue"
            apply_pdf_theme(theme_name)
        except Exception as e:
            print("load_settings error:", e)

    def show_bank_info_dialog(self):
        if not self.is_premium():
            self.show_bank_readonly_dialog()
            return
        L = self.current_lang
        box = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(500),
                        padding=[dp(10), dp(6), dp(10), dp(10)], spacing=dp(10))
        fields = []
        for key in ("bank_holder", "bank_name", "bank_agency", "bank_account"):
            lbl = MDLabel(text=self.trd(key), bold=True,
                          size_hint_y=None, height=dp(22), font_size="14sp",
                          halign="right" if L == "ar" else "left",
                          theme_text_color="Custom",
                          text_color=(0.08, 0.45, 0.75, 1))
            box.add_widget(lbl)
            tf = ArabicField(mode="rectangle", font_size="16sp")
            set_field_val(tf, self.get_setting(key))
            box.add_widget(tf)
            fields.append((key, tf))

        def save(_=None):
            conn = sqlite3.connect(get_db_path())
            for key, tf in fields:
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                             (key, field_val(tf).strip()))
            conn.commit()
            conn.close()
            self.bank_dialog.dismiss()
            self.bank_dialog = None
            self.notify(self.tr("bank_saved_success"))

        self.bank_dialog = self.dlg(
            title=self.trd("bank_section"), type="custom",
            content_cls=self.wrap_dialog(box),
            buttons=[self.btn_cancel(lambda x: self.bank_dialog.dismiss()),
                     self.btn_save("save", save)])
        self.bank_dialog.open()

    def show_bank_readonly_dialog(self):
        L = self.current_lang
        box = MDBoxLayout(orientation="vertical", size_hint_y=None,
                          spacing=dp(8), padding=[dp(8), dp(6), dp(8), dp(8)],
                          adaptive_height=True)
        box.add_widget(MDRaisedButton(
            text="Version gratuite" if L == "fr" else self.ar("النسخة المجانية"),
            md_bg_color=(0.95, 0.61, 0.07, 1),
            size_hint_y=None, height=dp(36),
            pos_hint={"center_x": 0.5},
            on_release=lambda x: (self.bank_dialog.dismiss(),
                                  self.show_upgrade_dialog("bank_locked"))))
        for key in ("bank_holder", "bank_name", "bank_agency", "bank_account"):
            val = self.get_setting(key) or "-"
            lbl = MDLabel(text=self.trd(key), bold=True,
                          size_hint_y=None, height=dp(20), font_size="13sp",
                          halign="right" if L == "ar" else "left",
                          theme_text_color="Custom", text_color=(0.08, 0.45, 0.75, 1))
            box.add_widget(lbl)
            val_lbl = MDLabel(text=self.ar(str(val)) if L == "ar" else str(val),
                              halign="right" if L == "ar" else "left",
                              size_hint_y=None, height=dp(24), font_size="15sp")
            val_lbl.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
            box.add_widget(val_lbl)
        self.bank_dialog = self.dlg(
            title=self.trd("bank_section"), type="custom",
            content_cls=self.wrap_dialog(box),
            buttons=[MDFlatButton(text=self.trd("close"),
                                  on_release=lambda x: self.bank_dialog.dismiss())])
        self.bank_dialog.open()

    def _color_label(self, theme_name, lang):
        return self.trd("color_" + theme_name, lang)

    def show_company_info_dialog(self):
        if not self.is_premium():
            self.show_company_readonly_dialog()
            return
        L = self.current_lang
        box = MDBoxLayout(orientation="vertical", size_hint_y=None,
                          spacing=dp(6), padding=[dp(8), dp(6), dp(8), dp(8)],
                          adaptive_height=True)
        box.add_widget(MDLabel(
            text=self.trd("company_color"), bold=True,
            size_hint_y=None, height=dp(22), font_size="14sp",
            halign="right" if L == "ar" else "left",
            theme_text_color="Custom", text_color=(0.08, 0.45, 0.75, 1)))
        theme_keys = ["blue", "green", "red", "purple", "teal", "maroon",
                      "gold", "black", "navy_dark", "white"]
        theme_labels = [self._color_label(k, L) for k in theme_keys]
        current_theme = self.get_setting("pdf_color") or "blue"
        try:
            current_idx = theme_keys.index(current_theme)
        except Exception:
            current_idx = 0
        color_spinner = Spinner(text=theme_labels[current_idx], values=theme_labels,
                                size_hint_y=None, height=dp(48),
                                background_color=(0.93, 0.96, 1, 1),
                                color=(0.1, 0.15, 0.25, 1), font_size="15sp")
        box.add_widget(color_spinner)
        box.add_widget(MDLabel(
            text=self.trd("company_logo"), bold=True,
            size_hint_y=None, height=dp(22), font_size="14sp",
            halign="right" if L == "ar" else "left",
            theme_text_color="Custom", text_color=(0.08, 0.45, 0.75, 1)))
        logo_row = BoxLayout(orientation="horizontal", size_hint_y=None,
                             height=dp(56), spacing=dp(8))
        logo_tf = MDTextField(mode="rectangle", readonly=True, font_size="12sp",
                              text=self.get_setting("company_logo") or "")
        logo_row.add_widget(logo_tf)

        def pick_logo(_=None):
            self._pick_company_logo(logo_tf)
        logo_row.add_widget(MDRaisedButton(
            text=self.trd("pick_logo"),
            md_bg_color=(0.55, 0.27, 0.68, 1),
            on_release=pick_logo))
        box.add_widget(logo_row)
        fields = []
        for key in ("company_name", "company_rc", "company_nif",
                    "company_phone", "company_address", "company_address_fr",
                    "company_city"):
            box.add_widget(MDLabel(
                text=self.trd(key), bold=True,
                size_hint_y=None, height=dp(22), font_size="14sp",
                halign="right" if L == "ar" else "left",
                theme_text_color="Custom", text_color=(0.08, 0.45, 0.75, 1)))
            tf = ArabicField(mode="rectangle", font_size="16sp")
            set_field_val(tf, self.get_setting(key))
            box.add_widget(tf)
            fields.append((key, tf))

        def save(_=None):
            sel = color_spinner.text
            try: tidx = theme_labels.index(sel)
            except Exception: tidx = 0
            tname = theme_keys[tidx]
            conn = sqlite3.connect(get_db_path())
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                         ("company_logo", clean_text(logo_tf.text).strip()))
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                         ("pdf_color", tname))
            for key, tf in fields:
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                             (key, field_val(tf).strip()))
            conn.commit()
            conn.close()
            apply_pdf_theme(tname)
            self.refresh_app_logo()
            self.refresh_app_title()
            self.company_dialog.dismiss()
            self.company_dialog = None
            self.notify(self.tr("bank_saved_success"))

        self.company_dialog = self.dlg(
            title=self.trd("company_section"), type="custom",
            content_cls=self.wrap_dialog(box),
            buttons=[self.btn_cancel(lambda x: self.company_dialog.dismiss()),
                     self.btn_save("save", save)])
        self.company_dialog.open()

    def show_company_readonly_dialog(self):
        L = self.current_lang
        info = self.get_company_info()
        box = MDBoxLayout(orientation="vertical", size_hint_y=None,
                          spacing=dp(8), padding=[dp(8), dp(6), dp(8), dp(8)],
                          adaptive_height=True)
        box.add_widget(MDRaisedButton(
            text="Version gratuite" if L == "fr" else self.ar("النسخة المجانية"),
            md_bg_color=(0.95, 0.61, 0.07, 1),
            size_hint_y=None, height=dp(36),
            pos_hint={"center_x": 0.5},
            on_release=lambda x: (self.company_dialog.dismiss(),
                                  self.show_upgrade_dialog("company_locked"))))
        fields = [
            ("company_name", info.get("name") or "-"),
            ("company_rc", info.get("rc") or "-"),
            ("company_nif", info.get("nif") or "-"),
            ("company_phone", info.get("phone") or "-"),
            ("company_address", info.get("address_ar") or "-"),
            ("company_address_fr", info.get("address_fr") or "-"),
            ("company_city", info.get("city") or "-"),
        ]
        for key, val in fields:
            lbl = MDLabel(text=self.trd(key), bold=True,
                          size_hint_y=None, height=dp(20), font_size="13sp",
                          halign="right" if L == "ar" else "left",
                          theme_text_color="Custom", text_color=(0.08, 0.45, 0.75, 1))
            box.add_widget(lbl)
            val_lbl = MDLabel(text=self.ar(str(val)) if L == "ar" else str(val),
                              halign="right" if L == "ar" else "left",
                              size_hint_y=None, height=dp(24), font_size="15sp")
            val_lbl.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
            box.add_widget(val_lbl)
        self.company_dialog = self.dlg(
            title=self.trd("company_section"), type="custom",
            content_cls=self.wrap_dialog(box),
            buttons=[MDFlatButton(text=self.trd("close"),
                                  on_release=lambda x: self.company_dialog.dismiss())])
        self.company_dialog.open()

    def _pick_company_logo(self, target_field):
        from kivy.utils import platform
        start = os.path.expanduser("~")
        if platform == "android":
            start = "/storage/emulated/0"
        from kivymd.uix.filemanager import MDFileManager

        def on_pick(path):
            try: self.file_manager.close()
            except Exception: pass
            if os.path.isfile(path):
                target_field.text = path

        def exit_mgr(*args):
            try: self.file_manager.close()
            except Exception: pass

        self.file_manager = MDFileManager(
            exit_manager=exit_mgr, select_path=on_pick,
            ext=[".png", ".jpg", ".jpeg"])
        self.file_manager.show(start)

    def get_company_info(self):
        info = {
            "logo": self.get_setting("company_logo"),
            "name": self.get_setting("company_name"),
            "rc": self.get_setting("company_rc"),
            "nif": self.get_setting("company_nif"),
            "phone": self.get_setting("company_phone"),
            "address_ar": self.get_setting("company_address"),
            "address_fr": self.get_setting("company_address_fr"),
            "city": self.get_setting("company_city"),
        }
        try:
            apply_pdf_theme(self.get_setting("pdf_color") or "blue")
        except Exception:
            pass
        return info

    def start_restore(self):
        self.open_file_manager("restore", [".db", ".sqlite"], self.tr("pick_backup_file"))

    def confirm_restore(self, path):
        self.restore_dialog = self.dlg(
            title=self.trd("restore_db"),
            text=ar_lines(self.tr("confirm_restore_msg"), max_chars=20),
            buttons=[MDFlatButton(text=self.trd("cancel"),
                                  on_release=lambda x: self.restore_dialog.dismiss()),
                     MDFlatButton(text=self.trd("restore_db"),
                                  text_color=(1, 0, 0, 1),
                                  on_release=lambda x: self.do_restore(path))])
        self.restore_dialog.open()

    def do_restore(self, path):
        self.restore_dialog.dismiss()
        try:
            chk = sqlite3.connect(path)
            names = {r[0] for r in chk.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            chk.close()
            if not {"cars", "clients", "contracts"} <= names:
                self.notify(self.tr("invalid_backup"))
                return
            self.backup_db("before_restore")
            src = sqlite3.connect(path)
            dst = sqlite3.connect(get_db_path())
            src.backup(dst)
            dst.close()
            src.close()
            init_db()
            self.load_cars()
            self.load_clients()
            self.load_contracts()
            self.load_settings()
            self.refresh_app_logo()
            self.refresh_app_title()
            self.refresh_premium_ui()
            self.refresh_security_btn()
            self.refresh_last_backup_text()
            self.notify(self.tr("db_restore_success"))
        except Exception as e:
            print("do_restore error:", e)
            self.notify(self.tr("save_error"))

    # ========== الإحصائيات ==========
    def show_stats(self):
        from kivy.uix.scrollview import ScrollView
        from kivy.uix.gridlayout import GridLayout
        conn = sqlite3.connect(get_db_path())
        c = conn.cursor()

        def sum_margin(sts):
            if not sts: return 0
            ph = ','.join('?' * len(sts))
            c.execute(f"SELECT COALESCE(SUM(CAST(profit_margin AS INTEGER)),0) FROM cars WHERE status IN ({ph})", sts)
            return int(c.fetchone()[0] or 0)

        pc = sum_margin([3]); pe = sum_margin([2, 3]); pt = sum_margin([1, 2, 3])
        c.execute("SELECT status, COUNT(*) FROM cars GROUP BY status")
        cs = dict(c.fetchall())
        avail, res, sold = cs.get(1, 0), cs.get(2, 0), cs.get(3, 0)
        c.execute("SELECT COUNT(*) FROM clients")
        cc = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM contracts")
        ctc = c.fetchone()[0]
        mp = datetime.datetime.now().strftime("%Y-%m")
        c.execute("SELECT COUNT(*) FROM contracts WHERE date LIKE ?", (mp + "%",))
        mc = c.fetchone()[0]
        c.execute("""SELECT clients.full_name, clients.full_name_fr, COUNT(*)
                     FROM contracts JOIN clients ON contracts.client_id = clients.id
                     GROUP BY clients.id ORDER BY COUNT(*) DESC LIMIT 1""")
        bc = c.fetchone()
        c.execute("""SELECT cars.name, cars.name_fr, COUNT(*)
                     FROM contracts JOIN cars ON contracts.car_id = cars.id
                     GROUP BY cars.id ORDER BY COUNT(*) DESC LIMIT 1""")
        bcar = c.fetchone()
        conn.close()
        L = self.current_lang

        def fmt(n):
            try: return f"{int(n):,}".replace(",", " ")
            except Exception: return str(n)

        bc_n = pick_name(bc[0], bc[1], L) if bc else "-"
        bc_c = bc[2] if bc else 0
        bcar_n = pick_name(bcar[0], bcar[1], L) if bcar else "-"
        bcar_c = bcar[2] if bcar else 0

        main = BoxLayout(orientation="vertical", size_hint_y=None,
                         spacing=dp(10), padding=[dp(4), dp(6), dp(4), dp(6)])
        main.bind(minimum_height=main.setter("height"))

        def make_section(tk, icon):
            card = MDCard(orientation="vertical", size_hint_y=None,
                          radius=[16], elevation=1, padding="10dp", spacing="8dp",
                          md_bg_color=(1, 1, 1, 1), adaptive_height=True)
            head = MDBoxLayout(orientation="horizontal", size_hint_y=None,
                               height=dp(30), spacing=dp(8))
            head.add_widget(MDIcon(icon=icon, theme_text_color="Custom",
                                   text_color=(0.08, 0.45, 0.75, 1),
                                   size_hint_x=None, width=dp(30)))
            head.add_widget(MDLabel(text=self.trd(tk), bold=True,
                                    font_size="16sp",
                                    halign="right" if L == "ar" else "left",
                                    theme_text_color="Custom",
                                    text_color=(0.08, 0.45, 0.75, 1)))
            card.add_widget(head)
            return card

        pcard = make_section("profit_section", "cash-multiple")
        pgrid = GridLayout(cols=3, spacing=dp(6), size_hint_y=None, height=dp(132))
        for icon, val, key, tint in [
            ("cash-check", fmt(pc), "profit_current", (0.15, 0.68, 0.38, 1)),
            ("chart-line", fmt(pe), "profit_expected", (0.95, 0.61, 0.07, 1)),
            ("cash-multiple", fmt(pt), "profit_total", (0.08, 0.45, 0.75, 1)),
        ]:
            pgrid.add_widget(StatCard(icon=icon, value=self.ar(val),
                                      unit=self.trd("million"),
                                      label=self.trd(key), tint=list(tint)))
        pcard.add_widget(pgrid)
        main.add_widget(pcard)

        ccard = make_section("cars_section", "car-multiple")
        cgrid = GridLayout(cols=3, spacing=dp(6), size_hint_y=None, height=dp(132))
        for icon, val, key, tint in [
            ("car", avail, "cars_available", (0.15, 0.68, 0.38, 1)),
            ("car-clock", res, "cars_reserved", (0.95, 0.61, 0.07, 1)),
            ("car-off", sold, "cars_sold", (0.75, 0.22, 0.17, 1)),
        ]:
            cgrid.add_widget(StatCard(icon=icon, value=self.ar(str(val)),
                                      unit="", label=self.trd(key), tint=list(tint)))
        ccard.add_widget(cgrid)
        main.add_widget(ccard)

        oc = make_section("contracts_section", "file-document-multiple")
        ogrid = GridLayout(cols=3, spacing=dp(6), size_hint_y=None, height=dp(132))
        for icon, val, key, tint in [
            ("file-document", ctc, "total_contracts", (0.55, 0.27, 0.68, 1)),
            ("calendar-month", mc, "month_contracts", (0.08, 0.45, 0.75, 1)),
            ("account-group", cc, "total_clients", (0.0, 0.55, 0.62, 1)),
        ]:
            ogrid.add_widget(StatCard(icon=icon, value=self.ar(str(val)),
                                      unit="", label=self.trd(key), tint=list(tint)))
        oc.add_widget(ogrid)
        main.add_widget(oc)

        tcard = make_section("top_section", "trophy")
        tl = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        tl.bind(minimum_height=tl.setter("height"))
        for icon, name, cnt in [("account-star", bc_n, bc_c), ("car-sports", bcar_n, bcar_c)]:
            row = MDBoxLayout(orientation="horizontal", size_hint_y=None,
                              height=dp(38), spacing=dp(8))
            row.add_widget(MDIcon(icon=icon, theme_text_color="Custom",
                                  text_color=(0.95, 0.61, 0.07, 1),
                                  size_hint_x=None, width=dp(30)))
            row.add_widget(MDLabel(text=self.ar(f"{name}  ({cnt} {self.tr('contract_n')})"),
                                   halign="right" if L == "ar" else "left",
                                   theme_text_color="Primary", font_size="14sp"))
            tl.add_widget(row)
        tcard.add_widget(tl)
        main.add_widget(tcard)

        sv = ScrollView(size_hint_y=None, height=dp(600), do_scroll_x=False)
        sv.add_widget(main)
        self.stats_dialog = self.dlg(
            title=self.trd("stat_dashboard"), type="custom", content_cls=sv,
            buttons=[MDFlatButton(text=self.trd("close"),
                                  on_release=lambda x: self.stats_dialog.dismiss())])
        self.stats_dialog.open()

    # ========== حول ==========
    def show_about(self):
        from kivy.uix.scrollview import ScrollView
        L = self.current_lang
        year = datetime.datetime.now().year
        badge = "PREMIUM" if self.is_premium() else "FREE"
        if L == "ar":
            text = (
                f"[size=20][b]Showroom Manager[/b][/size]\n\n"
                f"النسخة: {APP_VERSION} ({badge})\n\n"
                "[b]المطوّر[/b]\nكناف سمير\n\n"
                "[b]التواصل[/b]\nهاتف: +213 553 762 791\nبريد: kenefsamir0@gmail.com\n\n"
                "[b]سياسة الخصوصية[/b]\n"
                "هذا التطبيق لا يجمع أي بيانات شخصية.\n"
                "جميع البيانات تُخزَّن محلياً على جهازك.\n\n"
                "[b]شروط الاستخدام[/b]\n"
                "• التطبيق مرخّص لمستخدم واحد.\n"
                "• يُمنع إعادة توزيعه أو بيعه.\n\n"
                f"[size=12]جميع الحقوق محفوظة © {year}[/size]"
            )
        else:
            text = (
                f"[size=20][b]Showroom Manager[/b][/size]\n\n"
                f"Version: {APP_VERSION} ({badge})\n\n"
                "[b]Developpeur[/b]\nKenef Samir\n\n"
                "[b]Contact[/b]\nTel: +213 553 762 791\nEmail: kenefsamir0@gmail.com\n\n"
                "[b]Confidentialite[/b]\n"
                "Aucune donnee personnelle collectee.\n"
                "Toutes les donnees sont locales.\n\n"
                "[b]Conditions[/b]\n"
                "• Licence utilisateur unique.\n"
                "• Redistribution interdite.\n\n"
                f"[size=12]Tous droits reserves © {year}[/size]"
            )
        sv = ScrollView(size_hint_y=None, height=dp(400), do_scroll_x=False)
        lbl = MDLabel(text=self.ar_markup(text), markup=True,
                      halign="right" if L == "ar" else "left",
                      size_hint_y=None, theme_text_color="Primary")
        lbl.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
        lbl.bind(texture_size=lambda i, ts: setattr(i, "height", ts[1]))
        sv.add_widget(lbl)
        self.about_dialog = self.dlg(
            title=self.trd("about_title"), type="custom", content_cls=sv,
            buttons=[MDFlatButton(text=self.trd("close"),
                                  on_release=lambda x: self.about_dialog.dismiss())])
        self.about_dialog.open()

    # ========== PDF ==========
    def ask_payment_amount(self):
        self.contract_action_dialog.dismiss()
        if not self.get_setting("bank_account"):
            self.notify(self.tr("enter_bank_first"))
            return
        conn = sqlite3.connect(get_db_path())
        row = conn.execute("SELECT contract_price FROM contracts WHERE id=?", (self.current_contract_id,)).fetchone()
        conn.close()
        box = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(118),
                        padding=[dp(10), dp(6), dp(10), dp(8)], spacing=dp(6))
        box.add_widget(MDLabel(text=self.trd("amount_to_pay_hint"), size_hint_y=None,
                               height=dp(30), bold=True,
                               halign="right" if self.current_lang == "ar" else "left",
                               theme_text_color="Custom", text_color=(0.08, 0.45, 0.75, 1)))
        tf = ArabicField(text=loc_amount(row[0], self.current_lang) if row and row[0] else "",
                         mode="rectangle", font_size="17sp", icon_left="cash",
                         line_color_focus=(0.08, 0.45, 0.75, 1))
        box.add_widget(tf)
        self.pay_dialog = self.dlg(
            title=self.trd("payment_order"), type="custom",
            content_cls=self.wrap_dialog(box),
            buttons=[self.btn_cancel(lambda x: self.pay_dialog.dismiss()),
                     self.btn_save("gen_pdf", lambda x: self.make_payment_order(field_val(tf)))])
        self.pay_dialog.open()

    def make_payment_order(self, amount):
        amount = (amount or "").strip()
        if not amount:
            self.notify(self.tr("enter_amount"))
            return
        self.pay_dialog.dismiss()
        try:
            self.generate_payment_order(self.current_contract_id, amount)
            self.notify(self.tr("pay_pdf_success"))
        except Exception as e:
            print("pay_pdf error:", e)
            self.notify(self.tr("save_error"))

    def pdf_lang(self):
        return self.current_lang if self.current_lang in PDF_TR else "ar"

    def generate_payment_order(self, contract_id, amount):
        ci = self.get_company_info()
        conn = sqlite3.connect(get_db_path())
        row = conn.execute('''SELECT contracts.id, clients.full_name, clients.national_id, clients.address,
                                     cars.name, cars.trim, cars.color, cars.gearbox, cars.plate, cars.chassis,
                                     cars.mileage, cars.name_fr, clients.full_name_fr, clients.address_fr
                              FROM contracts JOIN cars ON contracts.car_id = cars.id
                              JOIN clients ON contracts.client_id = clients.id
                              WHERE contracts.id=?''', (contract_id,)).fetchone()
        if not row:
            conn.close()
            raise ValueError("Not found")
        cid, cname, cnid, caddr, car, trim, color, gearbox, plate, chassis, km, car_fr, cname_fr, caddr_fr = row
        cnt = conn.execute("""SELECT COUNT(*) FROM contracts
                              JOIN clients ON contracts.client_id = clients.id
                              WHERE clients.full_name=?""", (cname,)).fetchone()[0]
        conn.close()
        lang = self.pdf_lang()
        cname = pick_name(cname, cname_fr, lang)
        caddr = pick_name(caddr, caddr_fr, lang)
        car = pick_name(car, car_fr, lang)
        T = PDF_TR[lang]
        rtl = lang == "ar"
        d = lambda v: clean_text(v).strip() if v not in (None, '', 'None') else '-'
        amount = pdf_amount(amount, lang, add_unit=True)
        bank = {k: self.get_setting(k) for k in ("bank_holder", "bank_name", "bank_agency", "bank_account")}
        ds, ts = split_dt(None)
        cno = contract_number(cid, ds)
        safe = "".join(ch for ch in clean_text(cname or T["default_client"]) if ch not in '\\/:*?"<>|').strip() or T["default_client"]
        folder = doc_folder("pay", lang)
        out = os.path.join(folder, f"{T['f_pay']} - {safe}" + (f" - {cno}" if cnt > 1 else "") + ".pdf")
        fn = pdf_font()
        cv = canvas.Canvas(out, pagesize=A4)
        W, H = A4
        pdf_header(cv, fn, W, H, lang, company_info=ci)
        edge, al = pdf_edge(W, rtl)
        cv.setFillColor(NAVY)
        draw_text(cv, edge, H - 125, T["pay_title"], fn, 16, al)
        cv.setFillColor(colors.black)
        draw_text(cv, edge, H - 143, meta_line(T, rtl, cno, ds, ts), fn, 10, al)
        tables = [
            pdf_info_table(T["t_client_payer"], [
                (T["l_name"], d(cname)), (T["l_nid"], d(cnid)), (T["l_address"], d(caddr))], lang, fn),
            pdf_info_table(T["t_car_pay"], [
                (T["l_model"], d(car)), (T["l_trim"], d(trim)), (T["l_color"], d(loc_color(color, lang))),
                (T["l_gearbox"], loc_gearbox(gearbox, lang)), (T["l_plate"], d(plate)),
                (T["l_chassis"], d(chassis)), (T["l_km"], f"{d(km)} {T['km']}")], lang, fn),
            pdf_info_table(T["t_bank"], [
                (T["l_holder"], d(bank["bank_holder"])), (T["l_bank"], d(bank["bank_name"])),
                (T["l_agency"], d(bank["bank_agency"])), (T["l_rib"], d(bank["bank_account"]))], lang, fn),
            pdf_info_table(T["t_amount"], [
                (T["l_to_pay"], amount), (T["contract_no"], cno)], lang, fn),
        ]
        footer = lambda: pdf_footer(cv, fn, W, lang, company_info=ci)
        place_tables(cv, tables, H - 165, W, H, footer)
        draw_watermark(cv, W, H, ci, alpha=0.07)
        pdf_signatures(cv, fn, W, 190, lang, T["sig_payer"], T["sig_bank"])
        draw_qr(cv, qr_payload(("Ordre", cno), ("Date", f"{ds} {ts}".strip()),
                               ("Client", cname), ("Montant", amount),
                               ("Beneficiaire", bank["bank_holder"]),
                               ("RIB", bank["bank_account"])), W)
        footer()
        cv.save()
        return out

    def generate_order_pdf(self, contract_id, doc_path):
        import io, shutil
        ci = self.get_company_info()
        conn = sqlite3.connect(get_db_path())
        row = conn.execute('''SELECT contracts.id, contracts.date, clients.full_name, clients.national_id,
                                     clients.birth_info, clients.address,
                                     cars.name, cars.mileage, cars.trim, cars.color, cars.gearbox,
                                     cars.plate, cars.chassis, cars.name_fr,
                                     clients.full_name_fr, clients.address_fr
                              FROM contracts JOIN cars ON contracts.car_id = cars.id
                              JOIN clients ON contracts.client_id = clients.id
                              WHERE contracts.id=?''', (contract_id,)).fetchone()
        conn.close()
        if not row:
            raise ValueError("Not found")
        (cid, cdate, cname, cnid, cbirth, caddr, car, km, trim, color, gearbox,
         plate, chassis, car_fr, cname_fr, caddr_fr) = row
        cname_raw = cname
        lang = self.pdf_lang()
        cname = pick_name(cname, cname_fr, lang)
        caddr = pick_name(caddr, caddr_fr, lang)
        car = pick_name(car, car_fr, lang)
        T = PDF_TR[lang]
        rtl = lang == "ar"
        d = lambda v: clean_text(v).strip() if v not in (None, '', 'None') else '-'
        ds, ts = split_dt(cdate)
        cno = contract_number(cid, cdate)
        safe = "".join(ch for ch in clean_text(cname or T["default_client"]) if ch not in '\\/:*?"<>|').strip() or T["default_client"]
        folder = doc_folder("order", lang)
        conn = sqlite3.connect(get_db_path())
        cnt = conn.execute("""SELECT COUNT(*) FROM contracts
                              JOIN clients ON contracts.client_id = clients.id
                              WHERE clients.full_name=?""", (cname_raw,)).fetchone()[0]
        conn.close()
        suffix = f" - {cno}" if cnt > 1 else ""
        out = os.path.join(folder, f"{T['f_order']} - {safe}{suffix}.pdf")
        is_pdf = doc_path.lower().endswith(".pdf")
        tmp = os.path.join(folder, "_tmp.pdf") if is_pdf else out
        fn = pdf_font()
        cv = canvas.Canvas(tmp, pagesize=A4)
        W, H = A4
        pdf_header(cv, fn, W, H, lang, company_info=ci)
        edge, al = pdf_edge(W, rtl)
        cv.setFillColor(NAVY)
        draw_text(cv, edge, H - 120, T["order_title"], fn, 15, al)
        cv.setFillColor(colors.black)
        draw_text(cv, edge, H - 138, meta_line(T, rtl, cno, ds, ts), fn, 10, al)
        tables = [
            pdf_info_table(T["t_client"], [
                (T["l_name"], d(cname)), (T["l_nid"], d(cnid)),
                (T["l_birth"], d(cbirth)), (T["l_address"], d(caddr))], lang, fn),
            pdf_info_table(T["t_car_ordered"], [
                (T["l_model"], d(car)), (T["l_trim"], d(trim)), (T["l_color"], d(loc_color(color, lang))),
                (T["l_gearbox"], loc_gearbox(gearbox, lang)), (T["l_plate"], d(plate)),
                (T["l_chassis"], d(chassis)), (T["l_km"], f"{d(km)} {T['km']}")], lang, fn),
        ]
        footer = lambda: pdf_footer(cv, fn, W, lang, company_info=ci)
        y = place_tables(cv, tables, H - 160, W, H, footer)
        draw_watermark(cv, W, H, ci, alpha=0.07)
        cv.setFillColor(colors.black)
        y = draw_wrapped(cv, edge, y + 6, T["id_note"], fn, 9, al, W - 100, 13)
        sig = max(y - 30, 180)
        pdf_signatures(cv, fn, W, sig, lang, T["sig_company"])
        draw_qr(cv, qr_payload(("Commande", cno), ("Date", f"{ds} {ts}".strip()),
                               ("Client", cname), ("Vehicule", car), ("VIN", chassis)), W)
        footer()
        if not is_pdf:
            cv.showPage()
            cv.setFillColor(NAVY)
            draw_text(cv, edge, H - 50, T["id_page"].format(name=clean_text(cname or "")), fn, 14, al)
            from reportlab.lib.utils import ImageReader
            src = doc_path
            try:
                from PIL import Image as PILImage, ImageOps
                im = ImageOps.exif_transpose(PILImage.open(doc_path)).convert("RGB")
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=92)
                buf.seek(0)
                src = buf
            except Exception:
                pass
            iw, ih = ImageReader(src).getSize()
            if hasattr(src, "seek"): src.seek(0)
            mw, mh = W - 100, H - 160
            sc = min(mw / iw, mh / ih)
            w, h = iw * sc, ih * sc
            cv.drawImage(ImageReader(src), (W - w) / 2, H - 90 - h, w, h)
        cv.save()
        if is_pdf:
            try:
                try:
                    from pypdf import PdfReader, PdfWriter
                except ImportError:
                    from PyPDF2 import PdfReader, PdfWriter
                wr = PdfWriter()
                for pg in PdfReader(tmp).pages:
                    wr.add_page(pg)
                for pg in PdfReader(doc_path).pages:
                    wr.add_page(pg)
                with open(out, "wb") as f:
                    wr.write(f)
                os.remove(tmp)
            except ImportError:
                os.replace(tmp, out)
                shutil.copy(doc_path, os.path.join(folder, f"Piece - {safe}{suffix}.pdf"))
                self.notify(self.tr("pypdf_missing"))
        return out

    def reprint_pdf(self):
        self.contract_action_dialog.dismiss()
        self.generate_contract_pdf(self.current_contract_id)
        self.notify(self.tr("pdf_regenerated"))

    def delete_contract(self):
        self.contract_action_dialog.dismiss()
        conn = sqlite3.connect(get_db_path())
        row = conn.execute("SELECT paid_amount FROM contracts WHERE id=?", (self.current_contract_id,)).fetchone()
        conn.close()
        default = ""
        if row and row[0]:
            default = re.sub(r"(?i)\s*(مليون|millions?)\b", "", str(row[0])).strip()
        box = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(118),
                        padding=[dp(10), dp(6), dp(10), dp(8)], spacing=dp(6))
        box.add_widget(MDLabel(text=self.trd("cancel_refund_hint"), size_hint_y=None,
                               height=dp(30), bold=True,
                               halign="right" if self.current_lang == "ar" else "left",
                               theme_text_color="Custom", text_color=(0.08, 0.45, 0.75, 1)))
        tf = ArabicField(text=default, mode="rectangle", font_size="17sp",
                         icon_left="cash", line_color_focus=(0.08, 0.45, 0.75, 1))
        box.add_widget(tf)
        self.cancel_dialog = self.dlg(
            title=self.trd("cancel_contract_title"), type="custom",
            content_cls=self.wrap_dialog(box),
            buttons=[self.btn_cancel(lambda x: self.cancel_dialog.dismiss()),
                     self.btn_save("confirm_cancel", lambda x: self._do_cancel_contract(field_val(tf)))])
        self.cancel_dialog.open()

    def _do_cancel_contract(self, refund_text):
        self.cancel_dialog.dismiss()
        try:
            refund = (refund_text or "").strip()
            if not refund:
                self.notify(self.tr("cancel_refund_needed"))
                return
            if re.fullmatch(r"[\d\s.,]+", refund):
                refund = f"{refund} مليون"
            contract_id = self.current_contract_id
            self.generate_cancellation_pdf(contract_id, refund)
            conn = sqlite3.connect(get_db_path())
            c = conn.cursor()
            c.execute("SELECT car_id FROM contracts WHERE id=?", (contract_id,))
            row = c.fetchone()
            if row:
                c.execute("UPDATE cars SET status=1 WHERE id=?", (row[0],))
            c.execute("DELETE FROM contracts WHERE id=?", (contract_id,))
            conn.commit()
            conn.close()
            self.load_contracts()
            self.load_cars()
            self.notify(self.tr("cancel_pdf_success"))
        except Exception as e:
            print("cancel error:", e)
            self.notify(self.tr("save_error"))

    def generate_cancellation_pdf(self, contract_id, refund_amount):
        ci = self.get_company_info()
        conn = sqlite3.connect(get_db_path())
        row = conn.execute('''SELECT contracts.id, contracts.date,
                                     clients.full_name, clients.national_id, clients.address,
                                     cars.name, cars.plate, cars.chassis,
                                     cars.name_fr, clients.full_name_fr, clients.address_fr
                              FROM contracts JOIN cars ON contracts.car_id = cars.id
                              JOIN clients ON contracts.client_id = clients.id
                              WHERE contracts.id=?''', (contract_id,)).fetchone()
        conn.close()
        if not row:
            raise ValueError("Not found")
        (cid, cdate, cname, cnid, caddr, car, plate, chassis, car_fr, cname_fr, caddr_fr) = row
        lang = self.pdf_lang()
        cname = pick_name(cname, cname_fr, lang)
        caddr = pick_name(caddr, caddr_fr, lang)
        car = pick_name(car, car_fr, lang)
        T = PDF_TR[lang]
        rtl = lang == "ar"
        d = lambda v: clean_text(v).strip() if v not in (None, '', 'None') else '-'
        txt = lambda v: clean_text(v or "").strip()
        refund = pdf_amount(refund_amount, lang, add_unit=True)
        ds, ts = split_dt(None)
        when = T["when_dt"].format(d=ds, t=ts) if ts else T["when_d"].format(d=ds)
        cno = contract_number(cid, cdate)
        folder = doc_folder("cancel", lang)
        safe = "".join(ch for ch in clean_text(cname or T["default_client"])
                       if ch not in '\\/:*?"<>|').strip() or T["default_client"]
        out = os.path.join(folder, f"{T['canc_title']} - {safe} - {cno}.pdf")
        fn = pdf_font()
        cv = canvas.Canvas(out, pagesize=A4)
        W, H = A4
        edge, al = pdf_edge(W, rtl)
        footer = lambda: pdf_footer(cv, fn, W, lang, company_info=ci)
        pdf_header(cv, fn, W, H, lang, company_info=ci)
        cv.setFillColor(NAVY)
        draw_text(cv, edge, H - 118, T["canc_title"], fn, 14, al)
        cv.setFillColor(colors.black)
        draw_text(cv, edge, H - 136, meta_line(T, rtl, cno, ds, ts), fn, 10, al)
        cn = ci.get("name") or clean_text(T["company"])
        city = ci.get("city") or T["default_city"]
        ctx = dict(company=cn, city=city, name=txt(cname), nid=txt(cnid),
                   address=txt(caddr), cid=cno, car=txt(car),
                   chassis=d(chassis), plate=d(plate), refund=refund, when=when)
        y = H - 162
        bx = edge - 10 if rtl else edge + 10
        y = draw_wrapped(cv, bx, y, T["canc_intro"].format(**ctx), fn, 9.5, al, W - 130, 15)
        y -= 8
        for k in ("a1", "a2", "a3", "a4"):
            cv.setFillColor(colors.black)
            draw_text(cv, edge, y, T["canc_%s_t" % k], fn, 11, al)
            y -= 20
            y = draw_wrapped(cv, bx, y, T["canc_%s_b" % k].format(**ctx), fn, 9.5, al, W - 130, 15)
            y -= 10
        draw_watermark(cv, W, H, ci, alpha=0.07)
        sig = max(y - 40, 180)
        pdf_signatures(cv, fn, W, sig, lang, T["canc_sig_company"], T["canc_sig_client"])
        draw_qr(cv, qr_payload(("Resiliation", cno), ("Date", f"{ds} {ts}".strip()),
                               ("Client", cname), ("Refund", refund), ("Contrat", cno)), W)
        footer()
        cv.save()
        return out

    def generate_contract_pdf(self, contract_id):
        ci = self.get_company_info()
        conn = sqlite3.connect(get_db_path())
        c = conn.cursor()
        c.execute('''SELECT contracts.id, cars.name, cars.mileage, clients.full_name, clients.national_id,
                            clients.birth_info, clients.address, contracts.contract_price,
                            contracts.paid_amount, contracts.remaining_amount, contracts.date,
                            cars.color, cars.gearbox, cars.trim, cars.plate, cars.chassis,
                            cars.name_fr, clients.full_name_fr, clients.address_fr
                     FROM contracts JOIN cars ON contracts.car_id = cars.id
                     JOIN clients ON contracts.client_id = clients.id
                     WHERE contracts.id=?''', (contract_id,))
        data = c.fetchone()
        conn.close()
        if not data:
            return None
        (cid, car, km, cn, cnid, cb, caddr, price, paid, rem, cdate, ccolor, cgb,
         ctrim, cplate, cchassis, car_fr, c_fr, caddr_fr) = data
        cn_raw = cn
        lang = self.pdf_lang()
        cn = pick_name(cn, c_fr, lang)
        caddr = pick_name(caddr, caddr_fr, lang)
        car = pick_name(car, car_fr, lang)
        T = PDF_TR[lang]
        rtl = lang == "ar"
        d = lambda v: clean_text(v).strip() if v not in (None, '', 'None') else '-'
        txt = lambda v: clean_text(v or "").strip()
        price = pdf_amount(price, lang)
        paid = pdf_amount(paid, lang, add_unit=True)
        rem = pdf_amount(rem, lang, add_unit=True)
        ds, ts = split_dt(cdate)
        when = T["when_dt"].format(d=ds, t=ts) if ts else T["when_d"].format(d=ds)
        cno = contract_number(cid, cdate)
        folder = doc_folder("contract", lang)
        safe = "".join(ch for ch in clean_text(cn or T["default_client"])
                       if ch not in '\\/:*?"<>|').strip() or T["default_client"]
        conn = sqlite3.connect(get_db_path())
        cnt = conn.execute("""SELECT COUNT(*) FROM contracts
                              JOIN clients ON contracts.client_id = clients.id
                              WHERE clients.full_name=?""", (cn_raw,)).fetchone()[0]
        conn.close()
        fbase = f"{T['f_contract']} - {safe} - {cno}"
        fname = os.path.join(folder, fbase + ".pdf")
        fn = pdf_font()
        cpdf = canvas.Canvas(fname, pagesize=A4)
        W, H = A4
        edge, al = pdf_edge(W, rtl)
        footer = lambda: pdf_footer(cpdf, fn, W, lang, company_info=ci)
        qr = qr_payload(("Contrat", cno), ("Date", f"{ds} {ts}".strip()),
                        ("Client", cn), ("Vehicule", car), ("VIN", cchassis), ("Prix", price))

        pdf_header(cpdf, fn, W, H, lang, logo=False, company_info=ci)
        cpdf.setFillColor(NAVY)
        draw_text(cpdf, edge, H - 115, T["contract_title"], fn, 14, al)
        cpdf.setFillColor(colors.black)
        draw_text(cpdf, edge, H - 133, meta_line(T, rtl, cno, ds, ts), fn, 10, al)
        c_n = ci.get("name") or clean_text(T["company"])
        city = ci.get("city") or T["default_city"]
        ctx = dict(name=txt(cn), nid=txt(cnid), birth=txt(cb), address=txt(caddr),
                   car=txt(car), km=txt(km), trim=d(ctrim), color=d(loc_color(ccolor, lang)),
                   gearbox=loc_gearbox(cgb, lang), plate=d(cplate), chassis=d(cchassis),
                   price=price, when=when, company=c_n, city=city)

        custom_articles = get_contract_articles(lang)
        arts = []
        for art in custom_articles:
            title = art.get("title", "")
            body_tpl = art.get("body", "")
            try:
                body = body_tpl.format(**ctx)
            except Exception:
                body = body_tpl
            arts.append((title, body))

        y = H - 165
        bx = edge - 10 if rtl else edge + 10
        for t, b in arts:
            cpdf.setFillColor(colors.black)
            draw_text(cpdf, edge, y, t, fn, 11, al)
            y -= 20
            y = draw_wrapped(cpdf, bx, y, b, fn, 9.5, al, W - 130, 15)
            y -= 10
        draw_watermark(cpdf, W, H, ci, alpha=0.07)
        sig = max(y - 40, 180)
        pdf_signatures(cpdf, fn, W, sig, lang, T["sig_company"], T["sig_client"])
        draw_qr(cpdf, qr, W)
        footer()
        cpdf.showPage()

        cpdf.setFillColor(NAVY)
        draw_text(cpdf, edge, H - 45, T["receipt_title"], fn, 13, al)
        cpdf.setFillColor(colors.black)
        draw_text(cpdf, edge, H - 63, meta_line(T, rtl, cno, ds, ts), fn, 10, al)
        tables = [
            pdf_info_table(T["t_client"], [
                (T["l_name"], txt(cn)), (T["l_nid"], txt(cnid)),
                (T["l_address"], txt(caddr))], lang, fn),
            pdf_info_table(T["t_car"], [
                (T["l_model"], txt(car)), (T["l_trim"], d(ctrim)),
                (T["l_color"], d(loc_color(ccolor, lang))),
                (T["l_gearbox"], loc_gearbox(cgb, lang)), (T["l_plate"], d(cplate)),
                (T["l_chassis"], d(cchassis)), (T["l_km"], f"{txt(km)} {T['km']}")], lang, fn),
            pdf_info_table(T["t_fin"], [
                (T["l_price"], price), (T["l_paid"], paid), (T["l_remaining"], rem)],
                lang, fn, label_w=250, value_w=240,
                col_headers=(T["t_fin"], T["h_amount"])),
        ]
        place_tables(cpdf, tables, H - 90, W, H, footer)
        draw_watermark(cpdf, W, H, ci, alpha=0.07)
        pdf_signatures(cpdf, fn, W, 195, lang, T["sig_cashier"], T["sig_client_ok"])
        draw_qr(cpdf, qr, W)
        footer()
        cpdf.save()
        return fname

    def dlg(self, **kw):
        kw.setdefault("radius", [dp(24)] * 4)
        d = BigDialog(**kw)
        d.update_width()

        def _fix(*_):
            try: d.ids.title.font_name = self.font_file
            except Exception: pass
            try: d.ids.text.font_name = self.font_file
            except Exception: pass
            for key in ("title", "text"):
                try:
                    lbl = d.ids[key]
                    lbl.halign = "right" if self.current_lang == "ar" else "left"
                    lbl.text_size = (lbl.width, None)
                    lbl.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
                except Exception:
                    pass
        _fix()
        d.bind(on_pre_open=_fix)
        return d

    def wrap_dialog(self, content):
        from kivy.uix.scrollview import ScrollView
        from kivy.core.window import Window
        limit = Window.height * 0.72
        try: ch = content.height
        except Exception: ch = 0
        if ch and ch <= limit:
            return content
        sv = ScrollView(size_hint_y=None, do_scroll_x=False, height=limit)
        sv.add_widget(content)
        sv.scroll_y = 1
        return sv


# =====================================================================
#  نقطة الدخول
# =====================================================================
if __name__ == '__main__':
    try:
        AutoManagerApp().run()
    except Exception:
        err = traceback.format_exc()
        print("=" * 60)
        print("ERROR STARTUP:")
        print(err)
        print("=" * 60)
        try:
            # حفظ ملف الخطأ في مجلد التطبيق لسهولة الوصول إليه
            err_dir = app_storage_dir()
            with open(os.path.join(err_dir, "startup_error.txt"), "w", encoding="utf-8") as f:
                f.write(err)
        except Exception:
            pass