import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import json
import os
import sys
import subprocess
import logging
from clef_app.config import ConfigManager
from clef_app.logic.phase_1 import Phase1Runner
from clef_app.logic.phase_2 import Phase2Runner
from clef_app.logic.phase_3 import Phase3Runner
from clef_app.database import DatabaseManager
from clef_app.models import Proposal
from clef_app.html_utils import create_article_html

class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Clef - Article Wizard")
        self.geometry("1100x800")
        
        self.config_manager = ConfigManager()
        self.config = self.config_manager.config

        self.setup_styles()
        
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        self.create_settings_tab()
        self.create_articles_tab()
        self.create_phase1_tab()
        self.create_phase2_tab()
        self.create_phase3_tab()
        self.create_extras_tab()

    def setup_styles(self):
        style = ttk.Style(self)
        try:
            if 'clam' in style.theme_names():
                style.theme_use('clam')
        except:
            pass
            
        # Define colors and fonts
        bg_color = "#f8f9fa" 
        fg_color = "#212529"
        accent = "#007acc"
        header_bg = "#e9ecef"
        row_alt = "#f1f3f5"

        default_font = ('Segoe UI', 10)
        header_font = ('Segoe UI', 10, 'bold')

        style.configure(".", background=bg_color, foreground=fg_color, font=default_font)
        style.configure("TFrame", background=bg_color)
        
        # Notebook
        style.configure("TNotebook", background=bg_color)
        style.configure("TNotebook.Tab", background=header_bg, foreground=fg_color, padding=(12, 6), font=default_font)
        style.map("TNotebook.Tab", background=[("selected", bg_color)], expand=[("selected", [1, 1, 1, 0])])
        
        # LabelFrame
        style.configure("TLabelframe", background=bg_color, borderwidth=1, relief="solid")
        style.configure("TLabelframe.Label", font=header_font, foreground=accent, background=bg_color)
        
        # Button
        style.configure("TButton", font=default_font, padding=6, background=header_bg)
        style.map("TButton",
            background=[('active', '#dae0e5'), ('pressed', '#c0c0c0')],
            foreground=[('active', 'black')]
        )
        
        # Treeview
        style.configure("Treeview", 
            background="white", 
            fieldbackground="white", 
            foreground="black",
            rowheight=30,
            font=default_font,
            borderwidth=0
        )
        style.configure("Treeview.Heading", 
            font=header_font, 
            background=header_bg, 
            foreground=fg_color,
            padding=(10, 8)
        )
        style.map("Treeview", background=[("selected", accent)], foreground=[("selected", "white")])
        
        # Configure tags for Treeview
        # We need a reference to the style object or configure directly per treeview, 
        # but tags are configured on the Treeview widget itself. 
        # Here we just define the style configuration.

    def create_articles_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Articles DB")
        
        # Tools bar
        tools_frame = ttk.Frame(frame)
        tools_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(tools_frame, text="Refresh List", command=self.load_articles_list).pack(side='left')
        
        # Treeview
        columns = ('date', 'journal', 'title', 'slug')
        self.articles_tree = ttk.Treeview(frame, columns=columns, show='headings', selectmode='browse')
        
        # Configure striped rows
        self.articles_tree.tag_configure('odd', background='#f8f9fa')
        self.articles_tree.tag_configure('even', background='#e9ecef') # Slightly darker alternate
        self.articles_tree.tag_configure('selected', background='#007acc', foreground='white')
        
        self.articles_tree.heading('date', text='Date', anchor='w', command=lambda: self.sort_articles('date', False))
        self.articles_tree.heading('journal', text='Journal', anchor='w', command=lambda: self.sort_articles('journal', False))
        self.articles_tree.heading('title', text='Title', anchor='w', command=lambda: self.sort_articles('title', False))
        self.articles_tree.heading('slug', text='Slug', anchor='w', command=lambda: self.sort_articles('slug', False))
        
        self.articles_tree.column('date', width=100)
        self.articles_tree.column('journal', width=150)
        self.articles_tree.column('title', width=400)
        self.articles_tree.column('slug', width=200)
        
        self.articles_tree.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.articles_tree.yview)
        scrollbar.pack(side='right', fill='y')
        self.articles_tree.configure(yscrollcommand=scrollbar.set)
        
        # Bind double-click to view details
        self.articles_tree.bind("<Double-1>", self.on_article_select)
        
        self.load_articles_list()

    def sort_articles(self, col, reverse):
        l = [(self.articles_tree.set(k, col), k) for k in self.articles_tree.get_children('')]
        l.sort(reverse=reverse)

        # rearrange items in sorted positions
        for index, (val, k) in enumerate(l):
            self.articles_tree.move(k, '', index)
            
        # Refix striping
        for index, item in enumerate(self.articles_tree.get_children()):
            tag = 'even' if index % 2 == 0 else 'odd'
            self.articles_tree.item(item, tags=(tag,))

        # reverse sort next time
        self.articles_tree.heading(col, command=lambda: self.sort_articles(col, not reverse))

    def on_article_select(self, event):
        items = self.articles_tree.selection()
        if not items:
            return
            
        item = items[0]
        values = self.articles_tree.item(item, 'values')
        if not values:
            return
            
        date, journal, title, slug = values
        
        db = DatabaseManager()
        article = db.get_article_details(slug, journal)
        
        if not article:
            messagebox.showerror("Error", "Could not load article details.")
            return
            
        # Create detail window
        details_win = tk.Toplevel(self)
        details_win.title(f"Article: {article.get('title', 'Unknown')}")
        details_win.geometry("800x600")
        
        # Main info
        main_frame = ttk.Frame(details_win, padding=10)
        main_frame.pack(fill='both', expand=True)

        info_text = tk.Text(main_frame, wrap='word', font=('TkDefaultFont', 10))
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=info_text.yview)
        info_text.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side='right', fill='y')
        info_text.pack(side='left', fill='both', expand=True)
        
        # Populate text
        content = f"Title: {article.get('title', 'N/A')}\n"
        content += f"Journal: {article.get('journal', 'N/A')}\n"
        content += f"Date: {article.get('date', 'N/A')}\n"
        content += f"URL: {article.get('url', 'N/A')}\n"
        content += f"Category: {article.get('category', 'N/A')}\n"
        content += f"Style: {article.get('style', article.get('music_style', 'N/A'))}\n"
        content += f"Slug: {article.get('slug', 'N/A')}\n"
        content += "-" * 50 + "\n\n"
        
        content += "SUMMARY:\n"
        content += f"{article.get('summary', 'No summary available.')}\n\n"
        
        content += "-" * 50 + "\n\n"
        content += "FULL CONTENT:\n"
        content_txt = article.get('content', 'No content available.')
        # Limit content display if huge or implement truncation? For now show all.
        content += content_txt
        
        info_text.insert('1.0', content)
        info_text.configure(state='disabled') # Read-only

    def load_articles_list(self):
        for item in self.articles_tree.get_children():
            self.articles_tree.delete(item)
            
        db = DatabaseManager()
        articles = db.get_scraped_articles()
        for idx, art in enumerate(articles):
            tag = 'even' if idx % 2 == 0 else 'odd'
            self.articles_tree.insert('', 'end', values=(
                art['date'], art['journal'], art['title'], art['slug']
            ), tags=(tag,))
            
    def sort_articles(self, col, reverse):
        l = [(self.articles_tree.set(k, col), k) for k in self.articles_tree.get_children('')]
        l.sort(reverse=reverse)

        # rearrange items in sorted positions
        for index, (val, k) in enumerate(l):
            self.articles_tree.move(k, '', index)
            
        # Refix striping
        for index, item in enumerate(self.articles_tree.get_children()):
            tag = 'even' if index % 2 == 0 else 'odd'
            self.articles_tree.item(item, tags=(tag,))

        # reverse sort next time
        self.articles_tree.heading(col, command=lambda: self.sort_articles(col, not reverse))
        
    def create_settings_tab(self):
        # Create a container frame for the tab
        tab_frame = ttk.Frame(self.notebook)
        self.notebook.add(tab_frame, text="Settings")
        
        # Configure canvas + scrollbar for main settings area
        canvas = tk.Canvas(tab_frame, bg="#f8f9fa", highlightthickness=0)
        scrollbar = ttk.Scrollbar(tab_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Pack canvas and scrollbar into the tab_frame
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.widgets = {}

        # --- API Keys ---
        frame_api = ttk.LabelFrame(scrollable_frame, text="API Keys")
        frame_api.pack(fill='x', padx=10, pady=5)
        
        lbl_key = ttk.Label(frame_api, text="OpenAI API Key:")
        lbl_key.grid(row=0, column=0, padx=5, pady=5, sticky='w')
        entry_key = ttk.Entry(frame_api, width=50, show="*")
        entry_key.grid(row=0, column=1, padx=5, pady=5)
        entry_key.insert(0, self.config.get("api_keys", {}).get("openai_api_key", ""))
        self.widgets["openai_api_key"] = entry_key

        # --- WordPress ---
        frame_wp = ttk.LabelFrame(scrollable_frame, text="WordPress Configuration")
        frame_wp.pack(fill='x', padx=10, pady=5)
        
        wp_conf = self.config.get("wordpress", {})
        
        ttk.Label(frame_wp, text="WordPress URL:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        wp_url = ttk.Entry(frame_wp, width=40)
        wp_url.grid(row=0, column=1, padx=5, pady=5, sticky='w')
        wp_url.insert(0, wp_conf.get("url", ""))
        self.widgets["wp_url"] = wp_url
        
        ttk.Label(frame_wp, text="Username:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        wp_user = ttk.Entry(frame_wp, width=30)
        wp_user.grid(row=1, column=1, padx=5, pady=5, sticky='w')
        wp_user.insert(0, wp_conf.get("username", ""))
        self.widgets["wp_username"] = wp_user
        
        ttk.Label(frame_wp, text="App Password:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        wp_pass = ttk.Entry(frame_wp, width=30, show="*")
        wp_pass.grid(row=2, column=1, padx=5, pady=5, sticky='w')
        wp_pass.insert(0, wp_conf.get("application_password", ""))
        self.widgets["wp_password"] = wp_pass
        
        ttk.Button(frame_wp, text="Test Connection", command=self.test_wordpress).grid(row=3, column=1, sticky='e', padx=5, pady=5)


        # --- General Settings ---
        frame_gen = ttk.LabelFrame(scrollable_frame, text="General Settings")
        frame_gen.pack(fill='x', padx=10, pady=5)
        
        settings = self.config.get("settings", {})
        
        # Helper to create row
        def create_setting_row(parent, label, key, default, row):
            ttk.Label(parent, text=label).grid(row=row, column=0, padx=5, pady=5, sticky='w')
            e = ttk.Entry(parent)
            e.grid(row=row, column=1, padx=5, pady=5, sticky='w')
            e.insert(0, str(settings.get(key, default)))
            self.widgets[key] = e

        create_setting_row(frame_gen, "Days Lookback:", "days_lookback", 7, 0)
        create_setting_row(frame_gen, "Num Proposals:", "num_proposals", 5, 1)
        create_setting_row(frame_gen, "Num Images:", "num_images", 1, 2)
        create_setting_row(frame_gen, "Default Language:", "default_language", "italian", 3)
        create_setting_row(frame_gen, "LLM Model:", "llm_model", "openai/gpt-4o", 4)
        create_setting_row(frame_gen, "Temperature:", "llm_temperature", 0.3, 5)

        # --- Sources ---
        frame_sources = ttk.LabelFrame(scrollable_frame, text="Sources")
        frame_sources.pack(fill='x', padx=10, pady=5)
        
        # Sources Treeview
        columns_src = ('name', 'url')
        self.sources_tree = ttk.Treeview(frame_sources, columns=columns_src, show='headings', height=5, selectmode='browse')
        self.sources_tree.heading('name', text='Name')
        self.sources_tree.heading('url', text='URL')
        self.sources_tree.column('name', width=150)
        self.sources_tree.column('url', width=300)
        self.sources_tree.pack(fill='x', padx=5, pady=5)
        
        # Load existing sources
        for k, v in self.config.get("sources", {}).items():
            self.sources_tree.insert('', 'end', values=(k, v))
            
        # Add new source controls
        add_frame = ttk.Frame(frame_sources)
        add_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(add_frame, text="Name:").pack(side='left', padx=2)
        self.new_source_name = ttk.Entry(add_frame, width=15)
        self.new_source_name.pack(side='left', padx=5)
        
        ttk.Label(add_frame, text="URL:").pack(side='left', padx=2)
        self.new_source_url = ttk.Entry(add_frame, width=30)
        self.new_source_url.pack(side='left', padx=5)
        
        ttk.Button(add_frame, text="Add", command=self.add_source_to_list).pack(side='left', padx=5)
        ttk.Button(add_frame, text="Remove Selected", command=self.remove_source_from_list).pack(side='left', padx=5)


        # --- Prompts ---
        frame_prompts = ttk.LabelFrame(scrollable_frame, text="Prompts")
        frame_prompts.pack(fill='both', expand=True, padx=10, pady=5)
        
        self.prompt_widgets = {}
        prompts = self.config.get("prompts", {})
        
        # Add filtering / selection for prompts to avoid huge scroll
        self.prompt_var = tk.StringVar()
        prompt_keys = list(prompts.keys())
        if prompt_keys:
            self.prompt_var.set(prompt_keys[0])
            
        cbox_prompt = ttk.Combobox(frame_prompts, textvariable=self.prompt_var, values=prompt_keys, state="readonly")
        cbox_prompt.pack(fill='x', padx=5, pady=5)
        cbox_prompt.bind("<<ComboboxSelected>>", self.on_prompt_select)
        
        self.prompt_text = tk.Text(frame_prompts, height=10, font=('Segoe UI', 10), padx=5, pady=5, relief="solid", borderwidth=1)
        self.prompt_text.pack(fill='both', expand=True, padx=5, pady=5)
        if prompt_keys:
            self.prompt_text.insert('1.0', prompts[prompt_keys[0]])
            
        # Dictionary to hold current prompt edits in memory before save
        self.current_prompts_state = prompts.copy()
        self.prompt_text.bind("<KeyRelease>", self.update_prompt_state)

        btn_save = ttk.Button(scrollable_frame, text="Save All Settings", command=self.save_config)
        btn_save.pack(pady=20)
        
    def add_source_to_list(self):
        name = self.new_source_name.get().strip()
        url = self.new_source_url.get().strip()
        if name and url:
            self.sources_tree.insert('', 'end', values=(name, url))
            self.new_source_name.delete(0, 'end')
            self.new_source_url.delete(0, 'end')
            
    def remove_source_from_list(self):
        selected = self.sources_tree.selection()
        for item in selected:
            self.sources_tree.delete(item)

    def on_prompt_select(self, event):
        # When switching, make sure we captured the previous one? 
        # Actually update_prompt_state handles near-realtime, but let's be safe.
        # The prompt_var has the NEW value. Wait, how to get OLD value to save?
        # We need to track `self.last_selected_prompt`
        pass
        # Better: Since we update state on KeyRelease, we can just load the new one.
        key = self.prompt_var.get()
        self.prompt_text.delete('1.0', 'end')
        self.prompt_text.insert('1.0', self.current_prompts_state.get(key, ""))
        
    def update_prompt_state(self, event):
        key = self.prompt_var.get()
        if key:
            self.current_prompts_state[key] = self.prompt_text.get('1.0', 'end-1c')
            
    def test_wordpress(self):
        from clef_app.wordpress_client import WordPressClient
        url = self.widgets["wp_url"].get()
        user = self.widgets["wp_username"].get()
        pwd = self.widgets["wp_password"].get()
        
        if not url or not user or not pwd:
            messagebox.showwarning("Warning", "Please fill in all WordPress fields.")
            return

        client = WordPressClient(url, user, pwd)
        if client.validate_connection():
             messagebox.showinfo("Success", "Connection successful!")
        else:
             messagebox.showerror("Error", "Connection failed. Check credentials.")

    def add_source_to_list(self):
        name = self.new_source_name.get().strip()
        url = self.new_source_url.get().strip()
        if name and url:
            self.sources_tree.insert('', 'end', values=(name, url))
            self.new_source_name.delete(0, 'end')
            self.new_source_url.delete(0, 'end')
            
    def remove_source_from_list(self):
        selected = self.sources_tree.selection()
        for item in selected:
            self.sources_tree.delete(item)

    def save_config(self):
        try:
            # Sync current prompt text
            self.update_prompt_state(None)
            
            # --- API Keys ---
            new_api_keys = self.config.get("api_keys", {})
            new_api_keys["openai_api_key"] = self.widgets["openai_api_key"].get()
            
            # --- WordPress ---
            new_wordpress = {
                "url": self.widgets["wp_url"].get(),
                "username": self.widgets["wp_username"].get(),
                "application_password": self.widgets["wp_password"].get(),
            }
            
            new_config = {
                "api_keys": new_api_keys,
                "wordpress": new_wordpress,
                "settings": {
                    "days_lookback": int(self.widgets["days_lookback"].get()),
                    "num_proposals": int(self.widgets["num_proposals"].get()),
                    "num_images": int(self.widgets["num_images"].get()),
                    "default_language": self.widgets["default_language"].get(),
                    "llm_model": self.widgets["llm_model"].get(),
                    "llm_temperature": float(self.widgets["llm_temperature"].get())
                },
                "sources": {},
                "prompts": self.current_prompts_state
            }

            # Parse sources from Treeview
            new_config["sources"] = {}
            for item in self.sources_tree.get_children():
                name, url = self.sources_tree.item(item, 'values')
                new_config["sources"][name] = url

            self.config_manager.save_config(new_config)
            self.config = new_config
            messagebox.showinfo("Success", "Configuration saved!")
            
            # Re-read sources var for checkboxes
            # (Requires refreshing Phase 1 tab if we want it dynamic without restart, 
            # but for now a restart is often cleaner or we accept state desync until reopen)
            
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid number format: {e}")
        except Exception as e:
            messagebox.showerror("Error", f"Save failed: {e}")

    def create_phase1_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Phase 1: Scrape")
        
        lbl = ttk.Label(frame, text="Select Sources:")
        lbl.pack(anchor='w', padx=10, pady=5)
        
        self.sources_vars = {}
        sources_frame = ttk.Frame(frame)
        sources_frame.pack(fill='x', padx=10)
        
        sources = self.config.get("sources", {})
        for name in sources:
            var = tk.BooleanVar(value=True)
            chk = ttk.Checkbutton(sources_frame, text=name, variable=var)
            chk.pack(anchor='w')
            self.sources_vars[name] = var
            
        btn_run = ttk.Button(frame, text="Run Scraping", command=self.run_phase1)
        btn_run.pack(pady=20)
        
        # Log area with monospace font
        self.log_phase1 = tk.Text(frame, height=15, font=('Consolas', 9), bg="#f8f9fa", padx=10, pady=10, relief="solid", borderwidth=1)
        self.log_phase1.pack(fill='both', expand=True, padx=10, pady=10)

    def run_phase1(self):
        selected = [name for name, var in self.sources_vars.items() if var.get()]
        self.log_phase1.delete('1.0', 'end')
        
        logger = logging.getLogger("clef_app.gui")
        start_msg = f"Starting scraper for: {selected}...\n"
        logger.info(start_msg.strip())
        self.log_phase1.insert('end', start_msg)
        
        def update_log(msg):
            logger.info(msg)
            self.log_phase1.insert('end', msg + "\n")
            self.log_phase1.see('end')

        def task():
            runner = Phase1Runner()
            # Pass a lambda that schedules the update on main thread
            runner.run(selected, logger_callback=lambda msg: self.after(0, update_log, msg))
            self.after(0, update_log, "Done.")
            
        threading.Thread(target=task).start()

    def create_phase2_tab(self):
        self.p2_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.p2_frame, text="Phase 2: Proposals")
        
        # Simple layout: Left Frame (fixed width) and Right Frame (expand)
        left_panel = ttk.Frame(self.p2_frame, width=350)
        left_panel.pack(side='left', fill='y', padx=10, pady=10)
        left_panel.pack_propagate(False) # Force width
        
        # Interaction Header
        ttk.Label(left_panel, text="AI Assistant (Chat & Tools)").pack(anchor='w', padx=5, pady=5)
        
        # Chat area
        self.p2_chat = tk.Text(left_panel, height=20, width=40, state='disabled', font=('Segoe UI', 10), padx=5, pady=5, relief="flat", borderwidth=1, highlightthickness=1, highlightbackground="#ccc")
        self.p2_chat.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Input area
        input_frame = ttk.Frame(left_panel)
        input_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(input_frame, text="Msg:").pack(side='left')
        self.p2_input = ttk.Entry(input_frame, font=('Segoe UI', 10))
        self.p2_input.pack(side='left', fill='x', expand=True, padx=5)
        self.p2_input.bind('<Return>', lambda e: self.send_phase2_msg())
        
        ttk.Button(input_frame, text="Send", command=self.send_phase2_msg).pack(side='right')
        
        # Separator
        ttk.Separator(left_panel, orient='horizontal').pack(fill='x', padx=5, pady=10)
        
        # Buttons area
        btn_frame = ttk.Frame(left_panel)
        btn_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(btn_frame, text="Generate Initial Proposals", command=self.run_phase2_initial).pack(fill='x', pady=2)
        ttk.Button(btn_frame, text="Clear Chat", command=lambda: self.update_p2_chat("", clear=True)).pack(fill='x', pady=2)

        # Right side: Proposals Display
        right_panel = ttk.Frame(self.p2_frame)
        right_panel.pack(side='right', fill='both', expand=True, padx=10, pady=10)
        
        ttk.Label(right_panel, text="Generated Proposals List", font=('Segoe UI', 11, 'bold')).pack(anchor='w', padx=5, pady=5)
        
        # List of proposals titles
        self.proposals_listbox = tk.Listbox(right_panel, height=10, font=('Segoe UI', 10), activestyle='none', selectbackground='#007acc', selectforeground='white', borderwidth=1, relief="solid")
        self.proposals_listbox.pack(fill='x', expand=False, padx=5, pady=5)
        self.proposals_listbox.bind('<<ListboxSelect>>', self.on_proposal_select)
        
        # Details view
        ttk.Label(right_panel, text="Proposal Details", font=('Segoe UI', 11, 'bold')).pack(anchor='w', padx=5)
        self.proposal_details = tk.Text(right_panel, height=20, font=('Segoe UI', 10), padx=5, pady=5)
        self.proposal_details.pack(fill='both', expand=True, padx=5, pady=5)
        
        action_frame = ttk.Frame(right_panel)
        action_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(action_frame, text="Save Selected to DB", command=self.save_selected_proposal).pack(side='right')

        self.current_proposals = []
        self.p2_runner = Phase2Runner()

    def update_p2_chat(self, msg, sender="System", clear=False):
        self.p2_chat.config(state='normal')
        if clear:
            self.p2_chat.delete('1.0', 'end')
        
        logger = logging.getLogger("clef_app.gui.phase2")
        
        if msg:
            log_msg = f"{sender}: {msg}"
            logger.info(log_msg)
            self.p2_chat.insert('end', f"{log_msg}\n\n")
            self.p2_chat.see('end')
            
        self.p2_chat.config(state='disabled')

    def run_phase2_initial(self):
        self.update_p2_chat("Generating initial proposals... This may take a moment.")
        def task():
            try:
                # Get settings from UI widgets if possible or config
                # Ideally read from config directly as UI settings might not be saved
                days = self.config.get("settings", {}).get("days_lookback", 7)
                num = self.config.get("settings", {}).get("num_proposals", 5)
                
                proposals = self.p2_runner.generate_initial_proposals(days=days, num_proposals=num)
                self.after(0, self.handle_new_proposals, proposals, "Initial generation finished.")
            except Exception as e:
                self.after(0, self.update_p2_chat, f"Error: {e}")

        threading.Thread(target=task).start()

    def handle_new_proposals(self, proposals, msg):
        self.current_proposals.extend(proposals) # or replace? Script replaces usually or appends if 'more'.
        # If it's initial, likely replace.
        if msg.startswith("Initial"):
            self.current_proposals = proposals
        else:
            self.current_proposals.extend(proposals)
            
        self.update_p2_chat(f"{msg} Found {len(proposals)} new proposals.")
        self.refresh_proposals_list()

    def refresh_proposals_list(self):
        self.proposals_listbox.delete(0, 'end')
        for idx, p in enumerate(self.current_proposals):
            self.proposals_listbox.insert('end', f"{idx+1}. {p.title} ({p.category})")

    def on_proposal_select(self, event):
        sel = self.proposals_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < len(self.current_proposals):
            p = self.current_proposals[idx]
            # Dump readable details
            text = f"Title: {p.title}\nTheme: {p.theme}\nRationale: {p.rationale}\n\n"
            text += f"Key Elements: {', '.join(p.key_elements)}\n\n"
            text += "Related Articles:\n"
            for r in p.related_articles:
                text += f"- {r.title} ({r.slug})\n"
            
            self.proposal_details.delete('1.0', 'end')
            self.proposal_details.insert('1.0', text)

    def send_phase2_msg(self):
        msg = self.p2_input.get()
        if not msg: return
        self.p2_input.delete(0, 'end')
        self.update_p2_chat(msg, sender="User")
        
        def task():
            feedback = self.p2_runner.process_user_feedback(msg)
            self.after(0, self.handle_feedback_action, feedback)
            
        threading.Thread(target=task).start()

    def handle_feedback_action(self, feedback):
        action = feedback.action
        self.update_p2_chat(f"AI Action: {action}")
        
        if action == "request_more":
            # Generate more
            num = feedback.additional_requests if feedback.additional_requests else 2
            days = self.config.get("settings", {}).get("days_lookback", 7)
            self.update_p2_chat(f"Generating {num} more proposals...")
            
            def subtask():
                new_props = self.p2_runner.generate_more_proposals(days, num)
                self.after(0, self.handle_new_proposals, new_props, "Generated new proposals.")
            threading.Thread(target=subtask).start()
            
        elif action == "view_specific":
            idx = feedback.proposal_index
            if idx and 1 <= idx <= len(self.current_proposals):
                self.proposals_listbox.selection_clear(0, 'end')
                self.proposals_listbox.selection_set(idx-1)
                self.proposals_listbox.event_generate("<<ListboxSelect>>")
                self.update_p2_chat(f"Viewing proposal {idx}.")
            else:
                self.update_p2_chat("Invalid proposal index.")
        
        elif action == "approve":
             idx = feedback.proposal_index
             if idx:
                 self.save_proposal_by_index(idx-1)
                 self.update_p2_chat(f"Approved Proposal {idx}.")
             else:
                 self.update_p2_chat("Please specify which proposal to approve.")
                 
        elif action == "general_feedback":
             self.update_p2_chat(f"Notes taken: {feedback.feedback_text}")

    def save_proposal_by_index(self, idx):
        if 0 <= idx < len(self.current_proposals):
             p = self.current_proposals[idx]
             self.p2_runner.save_proposal(p)
             messagebox.showinfo("Saved", f"Proposal '{p.title}' saved to DB.")

    def save_selected_proposal(self):
        sel = self.proposals_listbox.curselection()
        if sel:
            self.save_proposal_by_index(sel[0])

    def create_phase3_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Phase 3: Write")
        
        # Load proposals from DB
        btn_load = ttk.Button(frame, text="Refresh Pending Proposals", command=self.load_pending_proposals)
        btn_load.pack(pady=5)
        
        self.pending_proposals_list = tk.Listbox(frame, height=8, font=('Segoe UI', 10), activestyle='none', selectbackground='#007acc', borderwidth=1, relief="solid")
        self.pending_proposals_list.pack(fill='x', padx=10, pady=5)
        
        lbl_lang = ttk.Label(frame, text="Language:")
        lbl_lang.pack()
        self.lang_var = tk.StringVar(value="italian")
        entry_lang = ttk.Entry(frame, textvariable=self.lang_var)
        entry_lang.pack()
        
        btn_write = ttk.Button(frame, text="Write Article", command=self.run_phase3)
        btn_write.pack(pady=10)
        
        self.log_phase3 = tk.Text(frame, height=15, font=('Consolas', 9), bg="#f8f9fa", padx=5, pady=5, relief="solid", borderwidth=1)
        self.log_phase3.pack(fill='both', expand=True, padx=10, pady=5)
        
        self.wp_var = tk.BooleanVar(value=True)
        self.cb_wp = ttk.Checkbutton(frame, text="Upload to WordPress as Draft", variable=self.wp_var)
        self.cb_wp.pack(pady=5)
        
        self.db_proposals = []
        
        # Image preview
        self.img_label = ttk.Label(frame, text="No Image Generated")
        self.img_label.pack(pady=10)

    def load_pending_proposals(self):
        from clef_app.database import DatabaseManager
        db = DatabaseManager()
        raw = db.get_proposals(status='pending')
        self.db_proposals = []
        self.pending_proposals_list.delete(0, 'end')
        for r in raw:
            # Reconstruct simplified object or use dict
            # We need to map it back to Proposal model if possible, or just use dict
            # Using dict is easier for now to pass data
            try:
                content = r['content']
                # If content is still a string (double encoded), try loading again
                if isinstance(content, str):
                    try:
                        content = json.loads(content)
                    except:
                        pass
                
                # Try to ensure it has minimal fields for Proposal
                if isinstance(content, dict):
                     # Add missing fields if necessary to avoid validation error
                     # but Proposal usually matches what we saved.
                     p_obj = Proposal(**content)
                     # Store full info including ID
                     r['p_obj'] = p_obj
                     self.db_proposals.append(r)
                     self.pending_proposals_list.insert('end', f"{r['id']}: {r['title']}")
                else:
                    print(f"Skipping proposal {r['id']}: content is not a dict: {type(content)}")
            except Exception as e:
                print(f"Error loading proposal {r['id']}: {e}")




    def run_phase3(self):
        sel = self.pending_proposals_list.curselection()
        if not sel:
            return
        idx = sel[0]
        proposal_record = self.db_proposals[idx]
        proposal = proposal_record['p_obj']
        lang = self.lang_var.get()
        
        # Ask user for destination folder first
        dest_folder = filedialog.askdirectory(title="Select Destination Folder for Article", mustexist=True)
        if not dest_folder:
            self.log_phase3.insert('end', "Operation cancelled: No folder selected.\n")
            return
            
        self.log_phase3.insert('end', f"Writing article for '{proposal.title}' in {lang}...\n")
        logger = logging.getLogger("clef_app.gui.phase3")
        logger.info(f"Starting write phase for proposal: {proposal.title}")

        upload_wp = self.wp_var.get()

        def task():
            runner = Phase3Runner()
            draft = runner.write_article(proposal, language=lang)
            # Use `app.after` to schedule UI updates on main thread
            self.after(0, lambda: self.on_article_generated(draft, dest_folder, proposal_record['id'], upload_wp))
            
        threading.Thread(target=task).start()

    def on_article_generated(self, draft, dest_folder, proposal_id, upload_wp=False):
        logger = logging.getLogger("clef_app.gui.phase3")
        
        if not draft:
            logger.error("Article generation returned None.")
            self.log_phase3.insert('end', "Error: Article generation returned None.\n")
            return
            
        import shutil
        import re
        try:
            from PIL import Image, ImageTk
        except ImportError:
            Image = None
            
        logger.info(f"Article generated: {draft.final_title}")
        self.log_phase3.insert('end', f"Article generated: {draft.final_title}\n")
        
        # Create safe slug folder
        safe_slug = re.sub(r'[^a-zA-Z0-9-]', '', draft.slug)
        article_dir = os.path.join(dest_folder, safe_slug)
        os.makedirs(article_dir, exist_ok=True)
        
        # Save HTML
        html_content = create_article_html(
            title=draft.final_title,
            subtitle=draft.subtitle,
            content=draft.final_content,
            image_path=draft.image_path if hasattr(draft, 'image_path') else None
        )
        html_file = "article.html"
        html_path = os.path.join(article_dir, html_file)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        self.log_phase3.insert('end', f"Saved HTML: {html_path}\n")

        # Save Social Posts
        social_dir = os.path.join(article_dir, "social")
        os.makedirs(social_dir, exist_ok=True)
        
        for i, post in enumerate(draft.social_posts):
             platform_safe = "".join(x for x in post.platform if x.isalnum())
             if not platform_safe:
                 platform_safe = "platform"
             post_filename = f"{i+1}_{platform_safe}.txt"
             post_path = os.path.join(social_dir, post_filename)
             
             with open(post_path, "w", encoding="utf-8") as f:
                 f.write(post.text)
                 
        self.log_phase3.insert('end', f"Saved social posts to: {social_dir}\n")
        
        # Save Image if present
        if draft.image_path and os.path.exists(draft.image_path):
            img_filename = os.path.basename(draft.image_path)
            dest_img_path = os.path.join(article_dir, img_filename)
            shutil.copy2(draft.image_path, dest_img_path)
            self.log_phase3.insert('end', f"Saved image: {dest_img_path}\n")
            
            # Display Image
            if Image:
                try:
                    pil_img = Image.open(dest_img_path)
                    pil_img.thumbnail((350, 350)) # Resize for UI
                    tk_img = ImageTk.PhotoImage(pil_img)
                    
                    self.img_label.config(image=tk_img, text="")
                    self.img_label.image = tk_img # Keep reference!
                except Exception as e:
                     self.log_phase3.insert('end', f"Error displaying image: {e}\n")
        else:
             self.img_label.config(text="No Image Generated", image='')
             
        # Upload to WordPress if requested
        if upload_wp:
            self.log_phase3.insert('end', "Uploading to WordPress...\n")
            
            def wp_task():
                wp_conf = self.config.get("wordpress", {})
                url = wp_conf.get("url")
                user = wp_conf.get("username")
                pwd = wp_conf.get("application_password")
                
                if not url or not user or not pwd:
                    self.log_phase3.insert('end', "Error: WordPress credentials missing.\n")
                    return
                
                from clef_app.wordpress_client import WordPressClient
                client = WordPressClient(url, user, pwd)
                
                # Verify connection and establish correct API route (standard vs query param)
                if not client.validate_connection():
                     self.log_phase3.insert('end', "❌ Connection Check Failed. Aborting Upload.\n")
                     return
                
                post_id = None
                
                # Upload Image if exists
                media_id = None
                if draft.image_path and os.path.exists(dest_folder): # dest_folder is parent dir
                     # Reconstruct path inside the saved folder
                     safe_slug = re.sub(r'[^a-zA-Z0-9-]', '', draft.slug)
                     article_path = os.path.join(dest_folder, safe_slug)
                     img_filename = os.path.basename(draft.image_path)
                     dest_img_path = os.path.join(article_path, img_filename)
                     
                     if os.path.exists(dest_img_path):
                         self.log_phase3.insert('end', f"Uploading image {img_filename}...\n")
                         res = client.upload_media(dest_img_path)
                         if res and 'id' in res:
                             media_id = res['id']
                             self.log_phase3.insert('end', f"Image uploaded. ID: {media_id}\n")
                         else:
                             self.log_phase3.insert('end', "Image upload failed.\n")
                
                # Upload Post
                self.log_phase3.insert('end', "Uploading draft post...\n")
                
                # Simple HTML formatting
                final_html = f"<h2>{draft.subtitle}</h2>\n\n"
                
                # Convert markdown paragraphs to basic HTML p tags
                content_html = draft.final_content.replace("\n\n", "</p><p>")
                content_html = f"<p>{content_html}</p>"
                
                full_content = final_html + content_html
                
                post = client.upload_draft(
                    title=draft.final_title,
                    content=full_content,
                    status='draft'
                )
                
                if post and 'id' in post:
                    post_id = post['id']
                    self.log_phase3.insert('end', f"✅ Post created successfully! ID: {post_id}\nLink: {post.get('link')}\n")
                    
                    if media_id:
                        success = client.update_post_featured_media(post_id, media_id)
                        if success:
                            self.log_phase3.insert('end', "Featured image set.\n")
                else:
                    self.log_phase3.insert('end', "❌ Error creating post.\n")

            threading.Thread(target=wp_task).start()

        # Update DB Status
        try:
             from clef_app.database import DatabaseManager
             db = DatabaseManager()
             db.update_proposal_status(proposal_id, 'completed')
             self.load_pending_proposals() # Refresh list
        except Exception as e:
             print(f"Error updating status: {e}")

        messagebox.showinfo("Success", f"Article saved to:\n{article_dir}")
        
        # Open folder in file manager
        try:
            if sys.platform == 'win32':
                os.startfile(article_dir)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', article_dir])
            else:
                subprocess.Popen(['xdg-open', article_dir])
        except Exception as e:
            logger.error(f"Error opening folder: {e}")
            self.log_phase3.insert('end', f"Error opening folder: {e}\n")

    def create_extras_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Extras")
        
        lbl = ttk.Label(frame, text="Generate Image from Text File")
        lbl.pack(pady=10)
        
        btn_upload = ttk.Button(frame, text="Upload Text File", command=self.upload_and_gen_image)
        btn_upload.pack()
        
        self.extras_log = tk.Text(frame, height=10, font=('Consolas', 9), bg="#f8f9fa", padx=5, pady=5, relief="solid", borderwidth=1)
        self.extras_log.pack(fill='both', expand=True, padx=10, pady=10)
        
    def upload_and_gen_image(self):
        path = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if not path:
            return
            
        # Ask where to save
        dest_dir = filedialog.askdirectory(title="Select Destination Folder for Image")
        if not dest_dir:
            return
            
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        logger = logging.getLogger("clef_app.gui.extras")
        self.extras_log.insert('end', f"Loaded {path}.\nDestination: {dest_dir}\nGenerating image...\n")
        logger.info(f"Generating image for file: {path}")
        
        def task():
            runner = Phase3Runner()
            # First, we need a prompt. Let's use LLM to extract prompt from text
            # and incorporate design guidelines from config
            
            from crewai import Agent, Task, Crew
            from clef_app.llm_provider import get_llm
            from clef_app.config import ConfigManager
            
            try:
                config = ConfigManager()
                design_guidelines = config.get("prompts", {}).get("design_image", "You are an AI image generator for an independent music magazine.")
                
                llm = get_llm()
                agent = Agent(
                    role="Image Prompt Creator",
                    goal="Create image prompts that respect design guidelines",
                    backstory=design_guidelines,
                    llm=llm
                )
                task_p = Task(
                    description=f"""
                    Analyze this article content and create a DALL-E image prompt.
                    
                    DESIGN GUIDELINES (YOU MUST FOLLOW THESE):
                    {design_guidelines}
                    
                    ARTICLE CONTENT:
                    {content[:1500]}
                    
                    Create an image prompt that:
                    - Captures the essence and key themes of the article
                    - RESPECTS and INCORPORATES the design guidelines above
                    - Is detailed and artistic
                    - Avoids anything prohibited by the design guidelines
                    """,
                    expected_output="A detailed image prompt that respects design guidelines",
                    agent=agent
                )
                crew = Crew(agents=[agent], tasks=[task_p])
                prompt_res = str(crew.kickoff())
                
                logger.info(f"Generated prompt: {prompt_res}")
                self.extras_log.insert('end', f"Generated Prompt: {prompt_res}\n")
                
                # Pass dest_dir to generate_image
                res = runner.generate_image(prompt_res, "extra_image", output_dir=dest_dir)
                logger.info(f"Image generation result: {res}")
                
                # If res contains "Image saved to: ...path...", extract path?
                # but we know the folder is dest_dir.
                self.extras_log.insert('end', f"Result: {res}\n")
                
                # Open folder
                try:
                    if sys.platform == 'win32':
                        os.startfile(dest_dir)
                    elif sys.platform == 'darwin':
                        subprocess.Popen(['open', dest_dir])
                    else:
                        subprocess.Popen(['xdg-open', dest_dir])
                except Exception as e:
                    logger.error(f"Error opening folder: {e}")
            except Exception as e:
                logger.error(f"Error in image generation task: {e}")
                self.extras_log.insert('end', f"Error: {e}\n")
            
        threading.Thread(target=task).start()

if __name__ == "__main__":
    app = MainApp()
    app.mainloop()
