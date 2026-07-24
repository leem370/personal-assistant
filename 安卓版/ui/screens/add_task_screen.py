"""添加任务页面。"""

import re

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivymd.uix.screen import MDScreen
from kivymd.uix.button import MDRaisedButton, MDFlatButton
from kivymd.uix.label import MDLabel
from kivymd.uix.snackbar import Snackbar
from kivymd.uix.textfield import MDTextField

from core import db


class AddTaskScreen(MDScreen):
    """添加任务页面。

    字段：任务名、类型（固定/弹性）、时间、时长（分钟）、周几、关联目标ID
    提交时调用 db.add_task(name, task_type, time, duration, days_of_week, goal_id)
    """

    # 时间格式验证：HH:MM
    _TIME_RE = re.compile(r"^[0-2]?\d:[0-5]\d$")
    # 周几格式验证：1-7 的逗号分隔
    _WEEKDAY_RE = re.compile(r"^[1-7](,[1-7])*$")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "add_task"

        layout = BoxLayout(orientation="vertical", padding=20, spacing=10)

        # 标题
        layout.add_widget(MDLabel(
            text="添加新任务", font_style="H5",
            halign="center", size_hint_y=None, height=50,
        ))

        # 表单区域（滚动）
        scroll = ScrollView()
        form = BoxLayout(orientation="vertical", size_hint_y=None, spacing=12)
        form.bind(minimum_height=form.setter("height"))

        # 任务名
        self.input_name = MDTextField(
            hint_text="任务名",
            max_text_length=30,
            size_hint_y=None, height=48,
        )
        form.add_widget(self.input_name)

        # 任务类型
        self.input_type = MDTextField(
            hint_text="类型（固定 / 弹性，默认固定）",
            text="固定",
            size_hint_y=None, height=48,
        )
        form.add_widget(self.input_type)

        # 时间
        self.input_time = MDTextField(
            hint_text="时间（如 09:00，弹性任务留空）",
            size_hint_y=None, height=48,
        )
        form.add_widget(self.input_time)

        # 时长
        self.input_duration = MDTextField(
            hint_text="时长（分钟，默认30）",
            text="30",
            size_hint_y=None, height=48,
        )
        form.add_widget(self.input_duration)

        # 周几
        self.input_weekday = MDTextField(
            hint_text="周几（如 1,3,5 表示周一三五，留空=每天）",
            size_hint_y=None, height=48,
        )
        form.add_widget(self.input_weekday)

        # 关联目标ID
        self.input_goal_id = MDTextField(
            hint_text="关联目标ID（可选）",
            size_hint_y=None, height=48,
        )
        form.add_widget(self.input_goal_id)

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
            text="保存",
            on_release=self.save_task,
        ))
        btn_layout.add_widget(MDFlatButton(
            text="返回",
            on_release=self.go_back,
        ))
        layout.add_widget(btn_layout)

        self.add_widget(layout)

    def on_enter(self):
        """进入页面时清空之前残留的错误反馈。"""
        self.feedback.text = ""

    def save_task(self, instance):
        """保存任务到数据库。"""
        name = self.input_name.text.strip()
        if not name:
            self.feedback.text = "任务名不能为空"
            return

        task_type = self.input_type.text.strip()
        if task_type not in ("固定", "弹性"):
            task_type = "固定"
        task_type_en = "fixed" if task_type == "固定" else "flexible"

        time_val = self.input_time.text.strip() or None
        if time_val and not self._TIME_RE.match(time_val):
            self.feedback.text = "时间格式不对，请用 HH:MM，如 09:00"
            return

        try:
            duration = int(self.input_duration.text.strip()) if self.input_duration.text.strip() else 30
        except ValueError:
            self.feedback.text = "时长必须是数字"
            return

        days_of_week = self.input_weekday.text.strip()
        if days_of_week and not self._WEEKDAY_RE.match(days_of_week):
            self.feedback.text = "周几格式不对，请用 1-7 的逗号分隔，如 1,3,5"
            return

        goal_id = None
        if self.input_goal_id.text.strip():
            try:
                goal_id = int(self.input_goal_id.text.strip())
            except ValueError:
                self.feedback.text = "目标ID必须是数字"
                return

        try:
            ok = db.add_task(name, task_type_en, time=time_val,
                             duration=duration, days_of_week=days_of_week,
                             goal_id=goal_id)
        except Exception as e:
            self.feedback.text = f"保存失败：{e}"
            return
        if ok:
            self.show_snackbar(f"已添加任务：{name}")
            self._clear_form()
            self.manager.current = "today"
        else:
            self.feedback.text = f"任务'{name}'已存在"

    def _clear_form(self):
        """清空表单。"""
        self.input_name.text = ""
        self.input_type.text = "固定"
        self.input_time.text = ""
        self.input_duration.text = "30"
        self.input_weekday.text = ""
        self.input_goal_id.text = ""
        self.feedback.text = ""

    def go_back(self, instance):
        self._clear_form()
        self.manager.current = "today"

    def show_snackbar(self, text, duration=2):
        """页面底部弹出一条提示。"""
        Snackbar(text=text, duration=duration).open()