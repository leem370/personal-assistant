"""今日待办页面。"""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivymd.uix.screen import MDScreen
from kivymd.uix.button import MDRaisedButton
from kivymd.uix.label import MDLabel
from kivymd.uix.list import MDList, OneLineListItem, TwoLineListItem
from kivymd.uix.snackbar import Snackbar

from core import db


class TodayScreen(MDScreen):
    """今日待办页面。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "today"

        layout = BoxLayout(orientation="vertical")

        # 标题
        title = MDLabel(
            text="今日待办",
            halign="center",
            font_style="H5",
            size_hint_y=None,
            height=60,
        )
        layout.add_widget(title)

        # 待办列表（滚动）
        scroll = ScrollView()
        self.task_list = MDList()
        scroll.add_widget(self.task_list)
        layout.add_widget(scroll)

        # 底部按钮
        btn_layout = BoxLayout(size_hint_y=None, height=80, spacing=10, padding=10)
        btn_layout.add_widget(MDRaisedButton(
            text="添加任务",
            on_release=self.goto_add_task,
        ))
        btn_layout.add_widget(MDRaisedButton(
            text="完成打卡",
            on_release=self.goto_complete,
        ))
        layout.add_widget(btn_layout)

        self.add_widget(layout)

    def on_enter(self):
        """页面进入时从数据库加载今日任务列表。"""
        self.task_list.clear_widgets()
        try:
            today_tasks = db.query_today_tasks()
        except Exception as e:
            self.show_snackbar(f"加载任务失败：{e}")
            return
        if not today_tasks:
            self.task_list.add_widget(OneLineListItem(text="今天没有待办任务"))
            return
        for t in today_tasks:
            task_type = "固定" if t["type"] == "fixed" else "弹性"
            time_str = t.get("time") or "弹性"
            duration = t.get("duration", 30)
            secondary = f"{task_type} · {time_str} · {duration}分钟"
            self.task_list.add_widget(TwoLineListItem(
                text=f"{t['name']}",
                secondary_text=secondary,
                on_release=lambda x, task=t: self.show_task_detail(task),
            ))

    def goto_add_task(self, instance):
        self.manager.current = "add_task"

    def goto_complete(self, instance):
        self.manager.current = "complete"

    def show_task_detail(self, task):
        """点击任务条目时弹出简要详情。"""
        lines = [
            f"任务：{task['name']}",
            f"类型：{'固定' if task['type'] == 'fixed' else '弹性'}",
        ]
        if task.get("time"):
            lines.append(f"时间：{task['time']}")
        lines.append(f"时长：{task.get('duration', 30)}分钟")
        if task.get("days_of_week"):
            lines.append(f"周几：{task['days_of_week']}")
        self.show_snackbar("\n".join(lines))

    def show_snackbar(self, text, duration=2):
        """页面底部弹出一条提示。"""
        Snackbar(text=text, duration=duration).open()
