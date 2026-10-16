# SPDX-License-Identifier: GPL-3.0-or-later
"""MQTT selection window owned by the existing theme preview."""
import logging
from pathlib import Path
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from .theme import save_widget


class SensorPanel:
    def __init__(self, root, service):
        self.root, self.service = root, service
        self.window = tk.Toplevel(root)
        self.window.transient(root)
        self.window.title('MQTT sensors - Theme editor')
        self.window.geometry('720x590')
        self.window.protocol('WM_DELETE_WINDOW', self.window.withdraw)
        self.ids = list(service.store.definitions)
        self.tree = ttk.Treeview(self.window, columns=('name', 'value', 'status'), show='headings', height=7)
        for column, label, width in [('name', 'Sensor', 300), ('value', 'Live value', 180), ('status', 'Status', 120)]:
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width)
        for key, item in service.store.definitions.items():
            self.tree.insert('', 'end', iid=key, values=(item.get('label', key), '', ''))
        self.tree.pack(fill='x', padx=12, pady=12)
        self.tree.selection_set(self.ids[0])
        self.tree.bind('<<TreeviewSelect>>', self.load_style)
        form = ttk.Frame(self.window)
        form.pack(fill='x', padx=12)
        self.kind = tk.StringVar(value='Text / number')
        ttk.Label(form, text='Widget type').grid(row=0, column=0, sticky='w')
        selector = ttk.Combobox(form, textvariable=self.kind,
                                values=['Text / number', 'Bar', 'History graph', 'Pie chart'], state='readonly')
        selector.grid(row=0, column=1, sticky='ew')
        selector.bind('<<ComboboxSelected>>', self.load_style)
        self.fields = {}
        for row, (name, label, value) in enumerate([
            ('X', 'X', '20'), ('Y', 'Y', '20'), ('WIDTH', 'Width', '220'),
            ('HEIGHT', 'Height', '40'), ('MIN_VALUE', 'Minimum', '0'),
            ('MAX_VALUE', 'Maximum', '100'), ('FONT_SIZE', 'Font size', '20'),
            ('RADIUS', 'Radius (X/Y = center)', '44')], 1):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky='w')
            variable = tk.StringVar(value=value)
            ttk.Entry(form, textvariable=variable).grid(row=row, column=1, sticky='ew', pady=2)
            self.fields[name] = variable
        form.columnconfigure(1, weight=1)
        ttk.Button(self.window, text='Save widget to theme', command=self.save).pack(pady=12)
        ttk.Label(self.window, text='Updates an existing widget of the same sensor and type.\n'
                  'Other theme settings remain editable in the YAML editor.').pack()
        self.status = tk.StringVar()
        ttk.Label(self.window, textvariable=self.status, wraplength=680).pack(padx=12, pady=10)
        # Reopen a hidden selection window without changing upstream window layout.
        root.bind('<Control-m>', lambda event: self.window.deiconify(), add='+')
        self.last_error = None
        root.after(1000, self.tick)

    def widget_kind(self):
        return {'Text / number': 'TEXT', 'Bar': 'GRAPH', 'History graph': 'LINE_GRAPH',
                'Pie chart': 'RADIAL'}[self.kind.get()]

    def load_style(self, event=None):
        from library import config
        selection = self.tree.selection()
        if not selection:
            return
        style = config.THEME_DATA.get('STATS', {}).get('CUSTOM', {}).get(selection[0], {}).get(self.widget_kind(), {})
        for key, variable in self.fields.items():
            if key in style:
                variable.set(str(style[key]))

    def save(self):
        from library import config
        try:
            key = self.tree.selection()[0]
            kind = self.widget_kind()
            if kind != 'TEXT' and self.service.store.definitions[key]['kind'] != 'number':
                raise ValueError('Bars, history graphs and pie charts require a numeric sensor.')
            values = {key: int(value.get()) for key, value in self.fields.items()}
            if min(values['X'], values['Y']) < 0 or min(values['WIDTH'], values['HEIGHT'], values['FONT_SIZE']) <= 0:
                raise ValueError('Positions must be non-negative and sizes must be positive.')
            if values['MIN_VALUE'] >= values['MAX_VALUE']:
                raise ValueError('Minimum must be less than maximum.')
            # Preserve any other styling already defined for this widget.
            style = dict(config.THEME_DATA.get('STATS', {}).get('CUSTOM', {}).get(key, {}).get(kind, {}))
            style.update(SHOW=True, X=values['X'], Y=values['Y'], WIDTH=values['WIDTH'], HEIGHT=values['HEIGHT'])
            style.setdefault('BACKGROUND_COLOR', '255, 255, 255')
            if kind == 'TEXT':
                style.update(FONT_SIZE=values['FONT_SIZE'])
                style.setdefault('FONT_COLOR', '0, 0, 0')
                style.setdefault('FONT', 'roboto-mono/RobotoMono-Regular.ttf')
            else:
                style.update(MIN_VALUE=values['MIN_VALUE'], MAX_VALUE=values['MAX_VALUE'])
                style.setdefault('BAR_COLOR' if kind in ('GRAPH', 'RADIAL') else 'LINE_COLOR', '30, 130, 200')
                if kind == 'LINE_GRAPH':
                    style.setdefault('AUTOSCALE', False)
                elif kind == 'RADIAL':
                    if values['RADIUS'] <= 0:
                        raise ValueError('Radius must be positive.')
                    style.update(RADIUS=values['RADIUS'], WIDTH=values['RADIUS'],
                                 ANGLE_START=0, ANGLE_END=360, ANGLE_SEP=0, ANGLE_STEPS=1,
                                 CLOCKWISE=True, SHOW_TEXT=False, DRAW_BAR_BACKGROUND=True)
                    style.setdefault('BAR_BACKGROUND_COLOR', '40, 70, 90')
            path = Path(config.THEME_DATA['PATH']) / 'theme.yaml'
            backup = save_widget(path, key, kind, style, page=config.THEME_DATA.get('_MQTT_PAGE_INDEX'))
            self.status.set(f'Saved. Backup: {backup.name}')
        except Exception as exc:
            messagebox.showerror('MQTT theme', str(exc), parent=self.window)

    def tick(self):
        main = sys.modules['__main__']
        try:
            for key in self.ids:
                reading = self.service.store.snapshot(key)
                self.tree.item(key, values=(self.service.store.definitions[key].get('label', key), reading.text, reading.status))
            if hasattr(main, 'viewer_picture'):
                # Only GUI thread touches Tk/Pillow/upstream rendering; MQTT callbacks update cache only.
                from PIL import ImageTk
                main.refresh_theme()
                picture = main.display.lcd.screen_image.copy()
                if main.config.THEME_DATA['display'].get('DISPLAY_SIZE', '3.5"') == '2.1"':
                    picture.paste(main.circular_mask, mask=main.circular_mask)
                factor = main.RESIZE_FACTOR
                image = ImageTk.PhotoImage(picture.resize((int(picture.width / factor), int(picture.height / factor))), master=self.root)
                main.viewer_picture.configure(image=image)
                main.display_image = image
                main.error_in_theme = False
            self.last_error = None
            self.status.set(self.service.store.status + ' - Live preview - Open sensor selection: Ctrl+M')
        except Exception as exc:
            message = str(exc)
            self.status.set('Preview error: ' + message)
            if message != self.last_error:
                logging.getLogger(__name__).warning('MQTT preview: %s', message)
            self.last_error = message
        finally:
            if self.root.winfo_exists():
                self.root.after(1000, self.tick)


def attach(root, service):
    # Called by after(), once the original editor has finished building its root.
    panel = SensorPanel(root, service)
    root._mqtt_panel = panel
