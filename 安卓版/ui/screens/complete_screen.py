"""完成打卡页面。"""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivymd.uix.screen import MDScreen
from kivymd.uix.button import MDRaisedButton, MDFlatButton
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField
from kivymd.uix.snackbar import Snackbar

from core import db


class CompleteScreen(MDScreen):
    """完成打卡页面。

    字段：选择任务、完成度%、专注分(0-10)、情绪、备注
    提交时调用 db.add_log(task_name, completion_rate, focus_score, mood, note)
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "complete"

        layout = BoxLayout(orientation="vertical", padding=20, spacing=10)

        # 标题
        layout.add_widget(MDLabel(
            text="完成打卡", font_style="H5",
            halign="center", size_hint_y=None, height=50,
        ))

        # 表单区域（滚动）
        scroll = ScrollView()
        form = BoxLayout(orientation="vertical", size_hint_y=None, spacing=12)
        form.bind(minimum_height=form.setter("height"))

        # 任务名
        self.input_task_name = MDTextField(
            hint_text="任务名",
            max_text_length=30,
            size_hint_y=None, height=48,
        )
        form.add_widget(self.input_task_name)

        # 完成度
        self.input_completion = MDTextField(
            hint_text="完成度%（0-100，默认100）",
            text="100",
            size_hint_y=None, height=48,
        )
        form.add_widget(self.input_completion)

        # 专注分
        self.input_focus = MDTextField(
            hint_text="专注分（0-10，默认7）",
            text="7",
            size_hint_y=None, height=48,
        )
        form.add_widget(self.input_focus)

        # 情绪
        self.input_mood = MDTextField(
            hint_text="情绪（好/一般/差，可选）",
            size_hint_y=None, height=48,
        )
        form.add_widget(self.input_mood)

        # 备注
        self.input_note = MDTextField(
            hint_text="备注（可选）",
            size_hint_y=None, height=48,
        )
        form.add_widget(self.input_note)

        scroll.add_widget(form)
        layout.add_widget(scroll)

        # 反馈标签
        self.feedback = MDLabel(
            text="", halign="center", theme_text_color="Error",
            size_hint_y=None, height=30,
        )
        layout.add_widget(self.feedback)

        # 按钮区
        btn_layout = BoxLayout(size_hint_y=None, height=60, spacing=10)
        btn_layout.add_widget(MDRaisedButton(
            text="提交",
            on_release=self.submit,
        ))
        btn_layout.add_widget(MDFlatButton(
            text="返回",
            on_release=self.go_back,
        ))
        layout.add_widget(btn_layout)

        self.add_widget(layout)

    def on_enter(self):
        """进入时先清空表单，再用今日第一个未完成任务预填任务名。"""
        self._clear_form()
        today_tasks = db.query_today_tasks()
        today_str = db.today_str()
        logs = db.query_logs_by_date(today_str)
        done = {l["task_name"] for l in logs if l["completion_rate"] > 0}
        uncompleted = [t for t in today_tasks if t["name"] not in done]
        if uncompleted:
            self.input_task_name.text = uncompleted[0]["name"]

    def submit(self, instance):
        """提交打卡到数据库。"""
        task_name = self.input_task_name.text.strip()
        if not task_name:
            self.feedback.text = "任务名不能为空"
            return

        try:
            completion = int(self.input_completion.text.strip())
            completion = max(0, min(100, completion))
        except ValueError:
            completion = 100

        try:
            focus = int(self.input_focus.text.strip())
            focus = max(0, min(10, focus))
        except ValueError:
            focus = 7

        mood = self.input_mood.text.strip() or None
        note = self.input_note.text.strip() or ""

        db.add_log(task_name, completion_rate=completion,
                   focus_score=focus, mood=mood, note=note)

        self.show_snackbar(f"✅ 已打卡：{task_name}")
        self.manager.current = "today"

    def _clear_form(self):
        """清空表单。"""
        self.input_task_name.text = ""
        self.input_completion.text = "100"
        self.input_focus.text = "7"
        self.input_mood.text = ""
        self.input_note.text = ""
        self.feedback.text = ""

    def go_back(self, instance):
        self._clear_form()
        self.manager.current = "today"

    def show_snackbar(self, text, duration=2):
        """页面底部弹出一条提示。"""
        Snackbar(text=text, duration=duration).open()