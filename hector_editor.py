import json
import os
import uuid
import urllib.request
import urllib.parse
import sys
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import customtkinter as ctk
from rdflib import Graph, URIRef

from hector_core import VocabularyManager

CONFIG_FILE = "hector_config.json"


class HECTOREditor:
    """
    Main controller class for the HECTOR-Editor.
    Manages user interactions and responsive GUI layout.
    Delegates all SKOS graph queries and modifications to VocabularyManager.
    """

    def __init__(self, root):
        self.root = root
        self.root.title("HECTOR-Editor")
        self.root.geometry("1350x920")

        # Instantiate business logic core
        self.mgr = VocabularyManager()
        
        self.current_file_path = ""
        self.scheme_uri = None
        self.parent_lookup = {}        
        self.delete_target_uri = None  
        self.search_popup = None
        self.wiki_window = None
        self.lang_popup = None
        self.import_align_uris = False

        # Multilingual ISO 639-1 language parameter registry
        self.all_possible_languages = ["de", "en", "fr", "es", "it", "la", "grc"]
        self.active_languages = ["de", "en"] 
        self.tree_lang = "de"  
        
        # Component caches mapping dynamic multilingual UI objects to runtime handlers
        self.lang_entries = {}      
        self.def_entries = {}       
        self.alt_label_frames = {}  
        self.alt_label_widgets = {} 

        self.entries = {}  

        # Initialize operational core subroutines
        self.load_config()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_app)
        self.build_ui()
        self.setup_styles()

        self.clear_all_editor_fields()
        if hasattr(self, 'remembered_path') and self.remembered_path and os.path.exists(self.remembered_path):
            self.load_data(self.remembered_path)

    def build_ui(self):
        """Constructs the high-level structural window geometry grid mapping."""
        self.root.grid_columnconfigure(0, weight=1, minsize=420)
        self.root.grid_columnconfigure(1, weight=2, minsize=750)
        self.root.grid_rowconfigure(0, weight=1)

        # =========================================================================
        # ---- LEFT WORKSPACE PANEL: GRAPH NAVIGATION TREE & FILE CONTROLS --------
        # =========================================================================
        self.left_frame = ctk.CTkFrame(self.root, corner_radius=15)
        self.left_frame.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")
        self.left_frame.grid_columnconfigure(0, weight=1)
        self.left_frame.grid_rowconfigure(9, weight=1) 

        # App Identity Block Container
        self.header_frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, padx=15, pady=(15, 5), sticky="ew")
        self.header_frame.grid_columnconfigure(0, weight=1)

        self.lbl_file_header = ctk.CTkLabel(self.header_frame, text="🏛️ HECTOR-EDITOR", font=("Arial", 12,))
        self.lbl_file_header.grid(row=0, column=0, sticky="w")

        self.switch_theme = ctk.CTkSwitch(self.header_frame, text="Dark Mode", command=self.toggle_theme, font=("Arial", 12))
        self.switch_theme.grid(row=0, column=1, sticky="e")
        if ctk.get_appearance_mode() == "Dark":
            self.switch_theme.select()

        # File System Initialization Triggers
        self.btn_open = ctk.CTkButton(self.left_frame, text="Open Main Vocabulary (.ttl)", command=self.open_file_dialog, fg_color="#2fa572", hover_color="#107c41", font=("Arial", 12))
        self.btn_open.grid(row=1, column=0, padx=15, pady=3, sticky="ew")

        # Create New Vocabulary
        self.btn_create_v = ctk.CTkButton(self.left_frame, text="✨ Create New Vocabulary", command=self.run_create_vocab, fg_color="#5a5a5a", hover_color="#454545", font=("Arial", 12))
        self.btn_create_v.grid(row=2, column=0, padx=15, pady=3, sticky="ew")

        self.btn_import_fac = ctk.CTkButton(self.left_frame, text="📥 Import Facet / Sub-Vocabulary (.ttl)", command=self.run_import_facet, fg_color="#1f538d", hover_color="#153b66", font=("Arial", 12))
        self.btn_import_fac.grid(row=3, column=0, padx=15, pady=3, sticky="ew")

        self.btn_export_fac = ctk.CTkButton(self.left_frame, text="📤 Export Selected Facet (.ttl)", command=self.run_export_facet, fg_color="#b87333", hover_color="#965c25", font=("Arial", 12))
        self.btn_export_fac.grid(row=4, column=0, padx=15, pady=3, sticky="ew")

        self.lbl_status = ctk.CTkLabel(self.left_frame, text="No vocabulary file loaded", text_color="gray", font=("Arial", 12))
        self.lbl_status.configure(text=os.path.basename(self.current_file_path) if self.current_file_path else "No vocabulary file loaded")
        self.lbl_status.grid(row=5, column=0, padx=15, pady=(5, 10), sticky="w")

        self.lbl_search_header = ctk.CTkLabel(self.left_frame, text="🔍 SEARCH & HIERARCHY", font=("Arial", 12))
        self.lbl_search_header.grid(row=6, column=0, padx=15, pady=(5, 0), sticky="w")

        # Search query row and tree language selection
        self.search_ctrl_frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        self.search_ctrl_frame.grid(row=7, column=0, padx=15, pady=5, sticky="ew")
        self.search_ctrl_frame.grid_columnconfigure(0, weight=3)
        self.search_ctrl_frame.grid_columnconfigure(1, weight=1)

        self.txt_search = ctk.CTkEntry(self.search_ctrl_frame, placeholder_text="Type to filter hierarchy...", font=("Arial", 12))
        self.txt_search.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        self.txt_search.bind("<KeyRelease>", lambda e: self.update_tree_ui())

        self.combo_tree_lang = ctk.CTkComboBox(self.search_ctrl_frame, width=80, font=("Arial", 12), values=[l.upper() for l in self.all_possible_languages], command=self.on_tree_lang_changed)
        self.combo_tree_lang.grid(row=0, column=1, sticky="ew")
        self.combo_tree_lang.set(self.tree_lang.upper())

        # Native Treeview Component Integration
        self.tree_container = ctk.CTkFrame(self.left_frame)
        self.tree_container.grid(row=9, column=0, padx=15, pady=15, sticky="nsew")
        self.tree_container.grid_columnconfigure(0, weight=1)
        self.tree_container.grid_rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(self.tree_container, show="tree", selectmode="browse")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_node_click)

        self.scrollbar = ttk.Scrollbar(self.tree_container, orient="vertical", command=self.tree.yview)
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=self.scrollbar.set)

        # =========================================================================
        # ---- RIGHT WORKSPACE PANEL: CONCEPT EDITOR METADATA FORM ----------------
        # =========================================================================
        self.right_frame = ctk.CTkScrollableFrame(self.root, corner_radius=15)
        self.right_frame.grid(row=0, column=1, padx=15, pady=15, sticky="nsew")
        self.right_frame.grid_columnconfigure(0, weight=1)

        self.lbl_editor = ctk.CTkLabel(self.right_frame, text="✏️ CONCEPT EDITOR", font=("Arial", 12))
        self.lbl_editor.grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")

        self.crud_btn_frame = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        self.crud_btn_frame.grid(row=1, column=0, padx=15, pady=5, sticky="ew")
        self.crud_btn_frame.grid_columnconfigure((0, 1), weight=1)

        self.btn_new_c = ctk.CTkButton(self.crud_btn_frame, text="➕ Create Concept", fg_color="#1f538d", hover_color="#153b66", height=30, font=("Arial", 12), command=self.run_prepare_new_concept)
        self.btn_new_c.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.btn_del_c = ctk.CTkButton(self.crud_btn_frame, text="🗑️ Delete Concept", fg_color="#a83232", hover_color="#7a2222", height=30, font=("Arial", 12), command=self.run_delete_concept)
        self.btn_del_c.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        self.form_frame = ctk.CTkFrame(self.right_frame, corner_radius=10, border_width=1)
        self.form_frame.grid(row=2, column=0, padx=15, pady=10, sticky="ew")
        self.form_frame.grid_columnconfigure(1, weight=1)

        self.rebuild_form_grid()

        self.btn_save = ctk.CTkButton(self.right_frame, text="💾 Commit Changes / Save Concept", fg_color="#2fa572", hover_color="#107c41", height=35, font=("Arial", 12), command=self.on_save)
        self.btn_save.grid(row=3, column=0, padx=15, pady=10, sticky="ew")

        self.lbl_tools = ctk.CTkLabel(self.right_frame, text="⚙️ DATA QUALITY CHECK", font=("Arial", 12))
        self.lbl_tools.grid(row=4, column=0, padx=15, pady=(15, 5), sticky="w")

        self.tools_btn_frame = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        self.tools_btn_frame.grid(row=5, column=0, padx=15, pady=5, sticky="ew")
        self.tools_btn_frame.grid_columnconfigure((0, 1), weight=1)

        self.btn_t_fix = ctk.CTkButton(self.tools_btn_frame, text="🛠️ Repair Missing URI Labels", height=28, font=("Arial", 12), command=self.run_fix_labels)
        self.btn_t_fix.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.btn_t_check = ctk.CTkButton(self.tools_btn_frame, text="🏥 Health Check", height=28, font=("Arial", 12), command=self.run_health_check)
        self.btn_t_check.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        self.out_tools = ctk.CTkTextbox(self.right_frame, height=270, fg_color="black", text_color="white", font=("Consolas", 16))
        self.out_tools.grid(row=6, column=0, padx=15, pady=(5, 15), sticky="ew")

    def toggle_theme(self):
        if self.switch_theme.get() == 1:
            ctk.set_appearance_mode("Dark")
        else:
            ctk.set_appearance_mode("Light")
        self.setup_styles()
        self.rebuild_form_grid()

    def on_tree_lang_changed(self, choice):
        self.tree_lang = choice.lower()
        self.update_tree_ui()

    def get_clean_namespace(self):
        return self.mgr.get_clean_namespace()

    def rebuild_form_grid(self):
        cached_vals = {}
        for k, v in self.entries.items():
            if hasattr(v, "winfo_exists") and v.winfo_exists():
                try: cached_vals[k] = v.get()
                except: pass

        cached_langs = {}
        for k, v in self.lang_entries.items():
            if hasattr(v, "winfo_exists") and v.winfo_exists():
                try: cached_langs[k] = v.get()
                except: pass

        cached_defs = {}
        for k, v in self.def_entries.items():
            if hasattr(v, "winfo_exists") and v.winfo_exists():
                try: cached_defs[k] = v.get()
                except: pass
        
        cached_alt_labels = {}
        for lang, entries_list in self.alt_label_widgets.items():
            valid_strings = []
            for e in entries_list:
                if hasattr(e, "winfo_exists") and e.winfo_exists():
                    try:
                        val = e.get().strip()
                        if val: valid_strings.append(val)
                    except: pass
            if valid_strings:
                cached_alt_labels[lang] = valid_strings

        cached_parents = []
        if hasattr(self, "parent_widgets"):
            for e in self.parent_widgets:
                if hasattr(e, "winfo_exists") and e.winfo_exists():
                    try:
                        val = e.get().strip()
                        if val: cached_parents.append(val)
                    except: pass

        for widget in self.form_frame.winfo_children():
            widget.destroy()

        is_dark = (ctk.get_appearance_mode() == "Dark")
        bg_color = "#2b2b2b" if is_dark else "#eaeaea"
        text_color = "white" if is_dark else "black"

        self.form_frame.configure(fg_color=bg_color)
        self.form_frame.grid_columnconfigure(0, weight=0, minsize=180)
        self.form_frame.grid_columnconfigure(1, weight=1)
        self.form_frame.grid_columnconfigure(2, weight=0, minsize=170)

        for r in range(50):
            self.form_frame.grid_rowconfigure(r, weight=0, minsize=0)

        current_row = 0
        if not self.current_file_path:
            return

        tk.Label(self.form_frame, text="URI (Read-only):", font=("Arial", 12), bg=bg_color, fg=text_color, anchor="w").grid(row=current_row, column=0, padx=(15, 5), pady=3, sticky="w")
        self.entries["uri"] = ctk.CTkEntry(self.form_frame, height=28, font=("Arial", 12))
        self.entries["uri"].grid(row=current_row, column=1, columnspan=2, padx=(5, 15), pady=(15, 3), sticky="ew")
        if "uri" in cached_vals:
            self.entries["uri"].insert(0, cached_vals["uri"])
        self.entries["uri"].configure(state="disabled")
        current_row += 1

        tk.Label(self.form_frame, text="Languages:", font=("Arial", 12), bg=bg_color, fg=text_color, anchor="w").grid(row=current_row, column=0, padx=(15, 5), pady=4, sticky="w")
        display_text = f"Selected: {', '.join([l.upper() for l in self.active_languages])}"
        
        dropdown_btn_bg = "#4f4f4f" if is_dark else "#d1d1d1"
        dropdown_btn_hover = "#3a3a3a" if is_dark else "#c1c1c1"
        dropdown_btn_text = "white" if is_dark else "black"
            
        self.btn_lang_dropdown = ctk.CTkButton(
            self.form_frame, 
            text=f"{display_text}  ▼", 
            height=26, 
            font=("Arial", 12), 
            fg_color=dropdown_btn_bg, 
            hover_color=dropdown_btn_hover,
            text_color=dropdown_btn_text,
            command=self.toggle_language_dropdown_popup
        )
        self.btn_lang_dropdown.grid(row=current_row, column=1, padx=(5, 5), pady=4, sticky="ew")
        
        self.btn_wikidata = ctk.CTkButton(self.form_frame, text="🔍 Query Wikidata API", width=160, height=26, font=("Arial", 12), fg_color="#8a3ab9", hover_color="#6d2d93", command=self.fetch_from_wikidata)
        self.btn_wikidata.grid(row=current_row, column=2, padx=(5, 15), pady=4, sticky="e")
        current_row += 1

        self.lang_entries = {}
        self.alt_label_frames = {}
        self.alt_label_widgets = {}

        for lang in self.active_languages:
            lang_label_text = f"prefLabel ({lang.upper()}):"
            tk.Label(self.form_frame, text=lang_label_text, font=("Arial", 12), bg=bg_color, fg=text_color, anchor="w").grid(row=current_row, column=0, padx=(15, 5), pady=3, sticky="w")
            
            self.lang_entries[lang] = ctk.CTkEntry(self.form_frame, height=28, font=("Arial", 12))
            self.lang_entries[lang].grid(row=current_row, column=1, padx=(5, 5), pady=3, sticky="ew")
            if lang in cached_langs:
                self.lang_entries[lang].insert(0, cached_langs[lang])
            
            btn_add_alt = ctk.CTkButton(self.form_frame, text="+ Alt", width=60, height=26, fg_color="#3a3a3a", font=("Arial", 12), command=lambda l=lang: self.add_alt_label_row(l))
            btn_add_alt.grid(row=current_row, column=2, padx=(5, 15), pady=3, sticky="e")
            current_row += 1

            self.alt_label_widgets[lang] = []
            self.alt_label_frames[lang] = tk.Frame(self.form_frame, bg=bg_color)
            self.alt_label_frames[lang].grid(row=current_row, column=1, columnspan=2, padx=(5, 15), pady=0, sticky="ew")
            self.alt_label_frames[lang].grid_columnconfigure(0, weight=1)
            
            if lang in cached_alt_labels:
                for text_value in cached_alt_labels[lang]:
                    self.add_alt_label_row(lang, initial_text=text_value)
            current_row += 1

        self.def_entries = {}
        for lang in self.active_languages:
            def_label_text = f"definition ({lang.upper()}):"
            tk.Label(self.form_frame, text=def_label_text, font=("Arial", 12), bg=bg_color, fg=text_color, anchor="w").grid(row=current_row, column=0, padx=(15, 5), pady=3, sticky="w")
            
            self.def_entries[lang] = ctk.CTkEntry(self.form_frame, height=28, font=("Arial", 12))
            self.def_entries[lang].grid(row=current_row, column=1, columnspan=2, padx=(5, 15), pady=3, sticky="ew")
            if lang in cached_defs:
                self.def_entries[lang].insert(0, cached_defs[lang])
            current_row += 1

        tk.Label(self.form_frame, text="Parent(s):", font=("Arial", 12), bg=bg_color, fg=text_color, anchor="w").grid(row=current_row, column=0, padx=(15, 5), pady=4, sticky="w")
        
        self.parent_widgets = []
        self.first_parent_widget = ctk.CTkEntry(self.form_frame, height=28, font=("Arial", 12), placeholder_text="Type to find parent...")
        self.first_parent_widget.grid(row=current_row, column=1, padx=(5, 5), pady=4, sticky="ew")
        self.first_parent_widget.bind("<KeyRelease>", lambda e, ent=self.first_parent_widget: self.handle_entry_search(e, ent))
        self.parent_widgets.append(self.first_parent_widget)
        if cached_parents:
            self.first_parent_widget.insert(0, cached_parents[0])

        btn_frame = tk.Frame(self.form_frame, bg=bg_color)
        btn_frame.grid(row=current_row, column=2, padx=(5, 15), pady=4, sticky="e")
        
        self.btn_set_top = ctk.CTkButton(btn_frame, text="Top Concept", width=95, height=26, fg_color="#6e6e6e", hover_color="#525252", font=("Arial", 12), command=self.clear_parent_to_top)
        self.btn_set_top.pack(side="left", padx=(0, 5))

        btn_add_parent = ctk.CTkButton(btn_frame, text="+ Parent", width=65, height=26, fg_color="#3a3a3a", font=("Arial", 12), command=self.add_parent_row)
        btn_add_parent.pack(side="left")
        current_row += 1

        self.parent_frame = tk.Frame(self.form_frame, bg=bg_color)
        self.parent_frame.grid(row=current_row, column=1, columnspan=2, padx=(5, 15), pady=0, sticky="ew")
        self.parent_frame.grid_columnconfigure(0, weight=1)
        
        if cached_parents and len(cached_parents) > 1:
            for parent_val in cached_parents[1:]:
                self.add_parent_row(initial_text=parent_val)
        current_row += 1

        tk.Label(self.form_frame, text="Wikidata Match:", font=("Arial", 12), bg=bg_color, fg=text_color, anchor="w").grid(row=current_row, column=0, padx=(15, 5), pady=3, sticky="w")
        self.entries["match_wiki"] = ctk.CTkEntry(self.form_frame, height=28, font=("Arial", 12), placeholder_text="http://www.wikidata.org/entity/Q...")
        self.entries["match_wiki"].grid(row=current_row, column=1, columnspan=2, padx=(5, 15), pady=3, sticky="ew")
        if "match_wiki" in cached_vals: self.entries["match_wiki"].insert(0, cached_vals["match_wiki"])
        current_row += 1

        tk.Label(self.form_frame, text="Getty AAT Match:", font=("Arial", 12), bg=bg_color, fg=text_color, anchor="w").grid(row=current_row, column=0, padx=(15, 5), pady=3, sticky="w")
        self.entries["match_aat"] = ctk.CTkEntry(self.form_frame, height=28, font=("Arial", 12), placeholder_text="http://vocab.getty.edu/aat/...")
        self.entries["match_aat"].grid(row=current_row, column=1, columnspan=2, padx=(5, 15), pady=3, sticky="ew")
        if "match_aat" in cached_vals: self.entries["match_aat"].insert(0, cached_vals["match_aat"])
        current_row += 1

        tk.Label(self.form_frame, text="GND Match:", font=("Arial", 12), bg=bg_color, fg=text_color, anchor="w").grid(row=current_row, column=0, padx=(15, 5), pady=3, sticky="w")
        self.entries["match_gnd"] = ctk.CTkEntry(self.form_frame, height=28, font=("Arial", 12), placeholder_text="https://d-nb.info/gnd/...")
        self.entries["match_gnd"].grid(row=current_row, column=1, columnspan=2, padx=(5, 15), pady=(3, 15), sticky="ew")
        if "match_gnd" in cached_vals: self.entries["match_gnd"].insert(0, cached_vals["match_gnd"])

    def add_alt_label_row(self, lang, initial_text=""):
        is_dark = ctk.get_appearance_mode() == "Dark"
        bg_color = "#2b2b2b" if is_dark else "#eaeaea"
        
        row_frame = tk.Frame(self.alt_label_frames[lang], bg=bg_color)
        row_frame.pack(fill="x", pady=1)
        
        entry = ctk.CTkEntry(row_frame, placeholder_text=f"Synonym ({lang.upper()})...", height=24, font=("Arial", 12))
        entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        if initial_text: entry.insert(0, initial_text)
            
        self.alt_label_widgets[lang].append(entry)
        
        btn_del = ctk.CTkButton(row_frame, text="✕", width=20, height=24, fg_color="#5a2222", hover_color="#421414", font=("Arial", 12), command=lambda: self.remove_alt_label_row(lang, row_frame, entry))
        btn_del.pack(side="right")

    def remove_alt_label_row(self, lang, row_frame, entry_widget):
        if entry_widget in self.alt_label_widgets[lang]: 
            self.alt_label_widgets[lang].remove(entry_widget)
        row_frame.destroy()
        self.form_frame.update()

    def add_parent_row(self, initial_text=""):
        is_dark = ctk.get_appearance_mode() == "Dark"
        bg_color = "#2b2b2b" if is_dark else "#eaeaea"
        
        row_frame = tk.Frame(self.parent_frame, bg=bg_color)
        row_frame.pack(fill="x", pady=1)
        
        entry = ctk.CTkEntry(row_frame, placeholder_text="Type to find parent...", height=24, font=("Arial", 12))
        entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        entry.bind("<KeyRelease>", lambda e, ent=entry: self.handle_entry_search(e, ent))
        if initial_text: 
            entry.insert(0, initial_text)
            
        self.parent_widgets.append(entry)
        
        btn_del = ctk.CTkButton(row_frame, text="✕", width=20, height=24, fg_color="#5a2222", hover_color="#421414", font=("Arial", 12), command=lambda: self.remove_parent_row(row_frame, entry))
        btn_del.pack(side="right")

    def remove_parent_row(self, row_frame, entry_widget):
        if entry_widget in self.parent_widgets:
            self.parent_widgets.remove(entry_widget)
        row_frame.destroy()
        self.form_frame.update()

    def toggle_language_dropdown_popup(self):
        if self.lang_popup: self.lang_popup.destroy(); self.lang_popup = None; return
        x = self.btn_lang_dropdown.winfo_rootx()
        y = self.btn_lang_dropdown.winfo_rooty() + self.btn_lang_dropdown.winfo_height()
        self.lang_popup = ctk.CTkToplevel(self.root)
        self.lang_popup.wm_overrideredirect(True) 
        self.lang_popup.wm_geometry(f"{self.btn_lang_dropdown.winfo_width()}x280+{x}+{y}")
        self.lang_popup.lift()
        self.lang_popup.attributes("-topmost", True)
        self.lang_popup.bind("<FocusOut>", lambda e: self.close_language_dropdown_popup())

        scroll_frame = ctk.CTkScrollableFrame(self.lang_popup, label_text="Toggle View Languages:")
        scroll_frame.pack(fill="both", expand=True)

        self.checkbox_vars = {}
        for lang in self.all_possible_languages:
            self.checkbox_vars[lang] = ctk.BooleanVar(value=(lang in self.active_languages))
            cb = ctk.CTkCheckBox(scroll_frame, text=lang.upper(), variable=self.checkbox_vars[lang], command=self.on_checkbox_toggled, font=("Arial", 12))
            cb.pack(fill="x", padx=10, pady=4)

        separator = ctk.CTkFrame(scroll_frame, height=2, fg_color="gray")
        separator.pack(fill="x", pady=8, padx=5)

        add_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        add_frame.pack(fill="x", padx=5, pady=2)
        add_frame.grid_columnconfigure(0, weight=1)

        self.ent_new_lang_code = ctk.CTkEntry(add_frame, placeholder_text="New code...", height=26, font=("Arial", 12))
        self.ent_new_lang_code.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        btn_submit_lang = ctk.CTkButton(add_frame, text="＋", width=35, height=26, font=("Arial", 12), fg_color="#3a3a3a", command=self.run_register_new_language_to_pool)
        btn_submit_lang.grid(row=0, column=1, sticky="e")
        self.lang_popup.focus_set()

    def close_language_dropdown_popup(self):
        if self.lang_popup: self.lang_popup.destroy(); self.lang_popup = None

    def on_checkbox_toggled(self):
        self.active_languages = [lang for lang, var in self.checkbox_vars.items() if var.get()]
        if not self.active_languages: self.active_languages = ["en"] 
        display_text = f"Selected: {', '.join([l.upper() for l in self.active_languages])}"
        self.btn_lang_dropdown.configure(text=f"{display_text}  ▼")
        
        self.rebuild_form_grid()
        self.update_tree_ui() 

    def run_register_new_language_to_pool(self):
        code = self.ent_new_lang_code.get().strip().lower()
        if not code or code in self.all_possible_languages: return
        self.all_possible_languages.append(code)
        self.active_languages.append(code)
        self.close_language_dropdown_popup()
        
        if hasattr(self, 'combo_tree_lang'):
            self.combo_tree_lang.configure(values=[l.upper() for l in self.all_possible_languages])
            
        self.rebuild_form_grid()
        self.update_tree_ui()

    def fetch_from_wikidata(self):
        search_term = ""
        search_lang = "en"
        for lang in self.active_languages:
            if lang in self.lang_entries and self.lang_entries[lang].get().strip():
                search_term = self.lang_entries[lang].get().strip()
                search_lang = lang
                break
        if not search_term:
            messagebox.showwarning("Wikidata Search", "Please enter a concept label into the fields to execute API query!")
            return

        self.log(f"🌐 Querying Wikidata API (Scope: '{search_lang}') for: '{search_term}'...")
        encoded_term = urllib.parse.quote(search_term)
        api_url = f"https://www.wikidata.org/w/api.php?action=wbsearchentities&search={encoded_term}&language={search_lang}&format=json&limit=15"

        try:
            req = urllib.request.Request(api_url, headers={'User-Agent': 'HECTOR-Editor/1.0'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                results = data.get("search", [])
                if not results:
                    messagebox.showinfo("Wikidata Search", f"No records found for '{search_term}'.")
                    return
                self.open_wikidata_selection_window(results)
        except Exception as e: self.log(f"❌ API failure: {e}")

    def open_wikidata_selection_window(self, results):
        if self.wiki_window: self.wiki_window.destroy()
        self.wiki_window = ctk.CTkToplevel(self.root)
        self.wiki_window.title("Wikidata Entity Disambiguation")
        self.wiki_window.geometry("750x480")
        self.wiki_window.lift()
        self.wiki_window.attributes("-topmost", True)

        lbl = ctk.CTkLabel(self.wiki_window, text="Select the exact matching semantic authority node:", font=("Arial", 12))
        lbl.pack(pady=10)

        scroll_box = ctk.CTkScrollableFrame(self.wiki_window, width=700, height=380)
        scroll_box.pack(fill="both", expand=True, padx=15, pady=10)

        for match in results:
            q_id = match["id"]
            label = match.get("label", "No Label")
            desc = match.get("description", "No description available")
            concept_uri = match["concepturi"]

            frame_item = ctk.CTkFrame(scroll_box, fg_color=("white", "#2e2e2e"), corner_radius=8)
            frame_item.pack(fill="x", pady=4, padx=5)

            txt_info = f"🆔 {q_id} -- {label}\nScope Note: {desc}"
            lbl_info = ctk.CTkLabel(frame_item, text=txt_info, justify="left", anchor="w", wraplength=520, font=("Arial", 12))
            lbl_info.pack(side="left", padx=10, pady=5, fill="x", expand=True)

            btn_select = ctk.CTkButton(frame_item, text="Select Entity", width=100, font=("Arial", 12), command=lambda q=q_id, uri=concept_uri: self.process_selected_wikidata(q, uri))
            btn_select.pack(side="right", padx=10, pady=5)

    def process_selected_wikidata(self, q_id, wiki_uri):
        if self.wiki_window: self.wiki_window.destroy(); self.wiki_window = None
        self.log(f"🔄 Resolving global authority contexts and mapping identifiers for {q_id}...")
        languages_query = "|".join(self.active_languages)
        detail_url = f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids={q_id}&props=labels|descriptions|claims&languages={languages_query}&format=json"

        try:
            req = urllib.request.Request(detail_url, headers={'User-Agent': 'HECTOR-Editor/1.0'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                entity = data["entities"][q_id]

                labels = entity.get("labels", {})
                en_label = labels.get("en", {}).get("value", "")

                for lang in self.active_languages:
                    val = labels.get(lang, {}).get("value", "")
                    if lang in self.lang_entries and self.lang_entries[lang].winfo_exists():
                        self.lang_entries[lang].delete(0, "end")
                        if val: self.lang_entries[lang].insert(0, val)
                        elif lang == "en" and not en_label:
                            global_fallback = next(iter(labels.values()), {}).get("value", "")
                            self.lang_entries["en"].insert(0, global_fallback)

                descriptions = entity.get("descriptions", {})
                for lang in self.active_languages:
                    val = descriptions.get(lang, {}).get("value", "")
                    if lang in self.def_entries and self.def_entries[lang].winfo_exists():
                        self.def_entries[lang].delete(0, "end")
                        if val:
                            self.def_entries[lang].insert(0, val)

                if "match_wiki" in self.entries and self.entries["match_wiki"].winfo_exists():
                    self.entries["match_wiki"].delete(0, "end")
                    self.entries["match_wiki"].insert(0, wiki_uri)

                claims = entity.get("claims", {})
                if "match_aat" in self.entries and self.entries["match_aat"].winfo_exists():
                    self.entries["match_aat"].delete(0, "end")
                    if "P1014" in claims:
                        aat_id = claims["P1014"][0]["mainsnak"]["datavalue"]["value"]
                        self.entries["match_aat"].insert(0, f"http://vocab.getty.edu/aat/{aat_id}")

                if "match_gnd" in self.entries and self.entries["match_gnd"].winfo_exists():
                    self.entries["match_gnd"].delete(0, "end")
                    if "P227" in claims:
                        gnd_id = claims["P227"][0]["mainsnak"]["datavalue"]["value"]
                        self.entries["match_gnd"].insert(0, f"https://d-nb.info/gnd/{gnd_id}")
                self.log(f"✅ Context extraction finished for {q_id}.")
        except Exception as e: self.log(f"❌ Claim parsing disruption: {e}")

    def on_save(self):
        if "uri" not in self.entries or not self.entries["uri"].winfo_exists(): return
        uri_str = self.entries["uri"].get()
        if not uri_str or not self.current_file_path: return
        uri = URIRef(uri_str)

        # Retrieve prefLabels
        pref_labels = []
        for lang, widget in self.lang_entries.items():
            if widget.winfo_exists():
                text_val = widget.get().strip()
                if text_val: pref_labels.append((text_val, lang))

        # Retrieve altLabels
        alt_labels = []
        for lang, entries_list in self.alt_label_widgets.items():
            for ent_widget in entries_list:
                if ent_widget.winfo_exists():
                    alt_val = ent_widget.get().strip()
                    if alt_val: alt_labels.append((alt_val, lang))

        # Retrieve definitions
        definitions = []
        for lang, widget in self.def_entries.items():
            if widget.winfo_exists():
                text_val = widget.get().strip()
                if text_val: definitions.append((text_val, lang))

        # Retrieve exactMatch fields
        match_wiki = self.entries["match_wiki"].get().strip() if ("match_wiki" in self.entries and self.entries["match_wiki"].winfo_exists()) else ""
        match_aat = self.entries["match_aat"].get().strip() if ("match_aat" in self.entries and self.entries["match_aat"].winfo_exists()) else ""
        match_gnd = self.entries["match_gnd"].get().strip() if ("match_gnd" in self.entries and self.entries["match_gnd"].winfo_exists()) else ""

        # Retrieve parents
        broader_parents = []
        if hasattr(self, "parent_widgets"):
            for widget in self.parent_widgets:
                if widget.winfo_exists():
                    p_val = widget.get().strip()
                    if p_val and p_val in self.parent_lookup:
                        broader_parents.append(str(self.parent_lookup[p_val]))

        self.mgr.save_concept(uri, pref_labels, alt_labels, definitions, match_wiki, match_aat, match_gnd, broader_parents)
        self.update_tree_ui()
        self.log(f"💾 Graph synced to file: {self.get_label(uri, lang=self.tree_lang)}")
        self.display_turtle(uri)

    def on_tree_node_click(self, event):
        selected_item = self.tree.selection()
        if not selected_item: return
        uri = URIRef(self.tree.item(selected_item[0])["values"][0])
        
        self.rebuild_form_grid()
        self.clear_all_editor_fields()
        
        if "uri" in self.entries and self.entries["uri"].winfo_exists():
            self.entries["uri"].configure(state="normal")
            self.entries["uri"].insert(0, str(uri))
            self.entries["uri"].configure(state="disabled")
        
        # Load concept details via VocabularyManager
        details = self.mgr.get_concept_details(uri)

        # Auto-detect language additions
        for text_val, lang_code in details["pref_labels"]:
            if lang_code not in self.all_possible_languages:
                self.all_possible_languages.append(lang_code)
                
        for text_val, lang_code in details["alt_labels"]:
            if lang_code not in self.all_possible_languages:
                self.all_possible_languages.append(lang_code)

        for text_val, lang_code in details.get("definitions", []):
            if lang_code not in self.all_possible_languages:
                self.all_possible_languages.append(lang_code)

        # Populate prefLabels
        for text_val, lang_code in details["pref_labels"]:
            if lang_code in self.lang_entries and self.lang_entries[lang_code].winfo_exists():
                self.lang_entries[lang_code].delete(0, "end")
                self.lang_entries[lang_code].insert(0, text_val)

        # Populate altLabels
        for text_val, lang_code in details["alt_labels"]:
            self.add_alt_label_row(lang_code, initial_text=text_val)

        # Populate definitions
        for text_val, lang_code in details.get("definitions", []):
            if lang_code in self.def_entries and self.def_entries[lang_code].winfo_exists():
                self.def_entries[lang_code].delete(0, "end")
                self.def_entries[lang_code].insert(0, text_val)

        # Populate parents
        if hasattr(self, "parent_frame") and self.parent_frame.winfo_exists():
            parents = details["broaders"]
            if parents:
                if hasattr(self, "first_parent_widget") and self.first_parent_widget.winfo_exists():
                    self.first_parent_widget.delete(0, "end")
                    self.first_parent_widget.insert(0, self.get_label(URIRef(parents[0]), lang=self.tree_lang))
                for p in parents[1:]:
                    self.add_parent_row(initial_text=self.get_label(URIRef(p), lang=self.tree_lang))
        
        # Populate exactMatch fields
        if details["match_wiki"] and "match_wiki" in self.entries and self.entries["match_wiki"].winfo_exists(): 
            self.entries["match_wiki"].insert(0, details["match_wiki"])
        if details["match_aat"] and "match_aat" in self.entries and self.entries["match_aat"].winfo_exists(): 
            self.entries["match_aat"].insert(0, details["match_aat"])
        if details["match_gnd"] and "match_gnd" in self.entries and self.entries["match_gnd"].winfo_exists(): 
            self.entries["match_gnd"].insert(0, details["match_gnd"])
        self.display_turtle(uri)

    def clear_all_editor_fields(self):
        if "uri" in self.entries and self.entries["uri"].winfo_exists():
            self.entries["uri"].configure(state="normal")
            self.entries["uri"].delete(0, "end")
            self.entries["uri"].configure(state="disabled")
            
        for widget in self.lang_entries.values(): 
            if widget.winfo_exists(): widget.delete(0, "end")

        for widget in self.def_entries.values(): 
            if widget.winfo_exists(): widget.delete(0, "end")
            
        for frame in self.alt_label_frames.values():
            if frame.winfo_exists():
                for child in frame.winfo_children(): child.destroy()
                
        self.alt_label_widgets = {lang: [] for lang in self.all_possible_languages}
        for field in ["match_wiki", "match_aat", "match_gnd"]: 
            if field in self.entries and self.entries[field].winfo_exists():
                self.entries[field].delete(0, "end")
        if hasattr(self, "first_parent_widget") and self.first_parent_widget.winfo_exists():
            self.first_parent_widget.delete(0, "end")
        if hasattr(self, "parent_frame") and self.parent_frame.winfo_exists():
            for child in self.parent_frame.winfo_children():
                child.destroy()
        self.parent_widgets = [self.first_parent_widget] if hasattr(self, "first_parent_widget") else []

    def handle_entry_search(self, event, entry_widget):
        if not entry_widget.winfo_exists(): return
        val = entry_widget.get().lower().strip()
        if self.search_popup: self.search_popup.destroy(); self.search_popup = None
        if not val or not self.parent_lookup: return
        matches = [item for item in self.parent_lookup.keys() if val in item.lower()]
        if not matches: return
        x = entry_widget.winfo_rootx()
        y = entry_widget.winfo_rooty() + entry_widget.winfo_height()
        self.search_popup = ctk.CTkToplevel(self.root)
        self.search_popup.wm_overrideredirect(True)
        self.search_popup.wm_geometry(f"{entry_widget.winfo_width()}x150+{x}+{y}")
        scroll_box = ctk.CTkScrollableFrame(self.search_popup, label_text="Matches found:")
        scroll_box.pack(fill="both", expand=True)
        for match in matches[:30]:
            btn = ctk.CTkButton(scroll_box, text=match, anchor="w", fg_color="transparent", text_color=("black", "white"), hover_color=("#dbdbdb", "#2b2b2b"), height=24, font=("Arial", 12), command=lambda m=match: self.select_parent_from_popup(m, entry_widget))
            btn.pack(fill="x")

    def select_parent_from_popup(self, match_value, entry_widget):
        if entry_widget.winfo_exists():
            entry_widget.delete(0, "end")
            entry_widget.insert(0, match_value)
        if self.search_popup: self.search_popup.destroy(); self.search_popup = None

    def clear_parent_to_top(self):
        if hasattr(self, "first_parent_widget") and self.first_parent_widget.winfo_exists():
            self.first_parent_widget.delete(0, "end")
        if hasattr(self, "parent_frame") and self.parent_frame.winfo_exists():
            for child in self.parent_frame.winfo_children():
                child.destroy()
        self.parent_widgets = [self.first_parent_widget] if hasattr(self, "first_parent_widget") else []
        if self.search_popup: self.search_popup.destroy(); self.search_popup = None

    def load_config(self):
        self.remembered_path = ""
        appearance = "System"
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    cfg = json.load(f)
                    self.remembered_path = cfg.get("last_path", "")
                    appearance = cfg.get("theme", "System")
            except: pass
        ctk.set_appearance_mode(appearance)

    def save_config(self):
        cfg = {"last_path": self.current_file_path, "theme": ctk.get_appearance_mode()}
        try:
            with open(CONFIG_FILE, "w") as f: json.dump(cfg, f, indent=4)
        except: pass

    def setup_styles(self):
        style = ttk.Style()
        is_dark = ctk.get_appearance_mode() == "Dark"
        bg_color = "#2a2a2a" if is_dark else "#f0f0f0"
        fg_color = "#ffffff" if is_dark else "#000000"
        select_color = "#1f538d" if is_dark else "#add8e6"
        style.theme_use("default")
        style.configure("Treeview", background=bg_color, foreground=fg_color, fieldbackground=bg_color, rowheight=26, font=("Arial", 12))
        style.map("Treeview", background=[("selected", select_color)])

    def on_close_app(self):
        if self.search_popup: self.search_popup.destroy()
        if self.wiki_window: self.wiki_window.destroy()
        if self.lang_popup: self.lang_popup.destroy()
        self.save_config()
        self.root.destroy()

    def open_file_dialog(self):
        path = filedialog.askopenfilename(
            title="Open Vocabulary File",
            filetypes=[("Turtle Files", "*.ttl"), ("All Files", "*.*")]
        )
        if path: self.load_data(path)

    def log(self, message):
        print(message)
        if hasattr(self, 'out_tools') and self.out_tools.winfo_exists():
            self.out_tools.configure(state="normal")
            self.out_tools.insert("end", message + "\n")
            self.out_tools.see("end")  

    def display_turtle(self, uri):
        try:
            code = self.mgr.get_concept_turtle(uri)
            self.highlight_turtle_code(self.out_tools, code)
        except Exception as e:
            self.log(f"Error displaying concept code: {e}")

    def highlight_turtle_code(self, text_widget, code):
        text_widget.configure(state="normal")
        text_widget.delete("1.0", "end")
        text_widget.insert("1.0", code)
        
        is_dark = (ctk.get_appearance_mode() == "Dark")
        if is_dark:
            text_widget.tag_config("prefix", foreground="#569CD6")  # Blue
            text_widget.tag_config("uri", foreground="#4EC9B0")     # Teal
            text_widget.tag_config("literal", foreground="#CE9178") # Peach
            text_widget.tag_config("pref_label", foreground="yellow") # Yellow
            text_widget.tag_config("alt_label", foreground="orange")  # Orange
            text_widget.tag_config("comment", foreground="#6A9955") # Green
            text_widget.tag_config("keyword", foreground="#C586C0") # Purple
        else:
            text_widget.tag_config("prefix", foreground="#0000FF")  # Blue
            text_widget.tag_config("uri", foreground="#008080")     # Teal
            text_widget.tag_config("literal", foreground="#A31515") # Red
            text_widget.tag_config("pref_label", foreground="yellow") # Yellow (visible on black bg)
            text_widget.tag_config("alt_label", foreground="orange")  # Orange (visible on black bg)
            text_widget.tag_config("comment", foreground="#008000") # Green
            text_widget.tag_config("keyword", foreground="#7F007F") # Purple

        # Highlight tags using regex Tkinter search
        self.apply_regex_tag(text_widget, r"#.*", "comment")
        self.apply_regex_tag(text_widget, r"@prefix|PREFIX", "prefix")
        self.apply_regex_tag(text_widget, r'"[^"\\]*(?:\\.[^"\\]*)*"', "literal")
        self.apply_regex_tag(text_widget, r"@[a-zA-Z\-]+", "prefix")
        self.apply_regex_tag(text_widget, r"<[^>]+>", "uri")
        self.apply_regex_tag(text_widget, r"\ba\b", "keyword")
        
        # Highlight prefLabel and altLabel values specifically (added on top to override default literal tag)
        self.highlight_predicate_literals(text_widget, "skos:prefLabel", "pref_label")
        self.highlight_predicate_literals(text_widget, "skos:altLabel", "alt_label")
        
        text_widget.configure(state="disabled")

    def highlight_predicate_literals(self, text_widget, predicate, tag):
        start = "1.0"
        while True:
            idx = text_widget.search(predicate, start, stopindex="end")
            if not idx:
                break
            
            end_block_semi = text_widget.search(";", idx, stopindex="end")
            end_block_dot = text_widget.search(".", idx, stopindex="end")
            
            if end_block_semi and end_block_dot:
                if text_widget.compare(end_block_semi, "<", end_block_dot):
                    end_block = end_block_semi
                else:
                    end_block = end_block_dot
            else:
                end_block = end_block_semi or end_block_dot or "end"
                
            literal_pattern = r'"[^"\\]*(?:\\.[^"\\]*)*"'
            search_start = idx
            while True:
                lit_idx = text_widget.search(literal_pattern, search_start, stopindex=end_block, regexp=True)
                if not lit_idx:
                    break
                count = tk.IntVar()
                lit_idx = text_widget.search(literal_pattern, search_start, stopindex=end_block, regexp=True, count=count)
                match_len = max(1, count.get())
                lit_end = f"{lit_idx} + {match_len} chars"
                text_widget.tag_add(tag, lit_idx, lit_end)
                search_start = lit_end
                
            start = f"{idx} + {len(predicate)} chars"

    def apply_regex_tag(self, text_widget, pattern, tag):
        start = "1.0"
        while True:
            idx = text_widget.search(pattern, start, stopindex="end", regexp=True)
            if not idx:
                break
            count = tk.IntVar()
            idx = text_widget.search(pattern, start, stopindex="end", regexp=True, count=count)
            match_len = max(1, count.get())
            end_idx = f"{idx} + {match_len} chars"
            text_widget.tag_add(tag, idx, end_idx)
            start = end_idx

    def load_data(self, path):
        self.current_file_path = path
        try:
            detected_langs = self.mgr.load_data(path)
            self.scheme_uri = self.mgr.scheme_uri
            self.delete_target_uri = None
            self.lbl_status.configure(text=os.path.basename(path))
            
            self.all_possible_languages = detected_langs
            
            if hasattr(self, 'combo_tree_lang'):
                self.combo_tree_lang.configure(values=[l.upper() for l in self.all_possible_languages])
                if "de" in detected_langs: self.tree_lang = "de"
                elif "en" in detected_langs: self.tree_lang = "en"
                else: self.tree_lang = self.all_possible_languages[0]
                self.combo_tree_lang.set(self.tree_lang.upper())
            
            self.rebuild_form_grid()
            self.clear_all_editor_fields()
            self.update_tree_ui()
            self.log(f"🏛 *Vocabulary imported safely:* {os.path.basename(path)}")
        except Exception as e: messagebox.showerror("IO Error", f"Could not load graph file:\n{e}")

    def get_label(self, uri, lang=None):
        return self.mgr.get_label(uri, lang, self.active_languages, self.all_possible_languages)

    def update_tree_ui(self):
        """Rebuilds UI tree but strictly retains user fold expansion states and selection coordinates."""
        expanded_uris = set()
        selected_uri = None
        
        # Iterative capture of tree state
        state_stack = list(self.tree.get_children(""))
        while state_stack:
            item = state_stack.pop()
            vals = self.tree.item(item)["values"]
            if vals:
                uri_str = str(vals[0])
                if self.tree.item(item, "open"):
                    expanded_uris.add(uri_str)
            for child in self.tree.get_children(item):
                state_stack.append(child)
            
        sel = self.tree.selection()
        if sel and self.tree.item(sel[0])["values"]:
            selected_uri = str(self.tree.item(sel[0])["values"][0])

        for item in self.tree.get_children(): self.tree.delete(item)
        filter_txt = self.txt_search.get().lower().strip()
        concepts = self.mgr.get_concepts()
        
        roots = sorted(list(self.mgr.get_roots()), key=lambda x: self.get_label(x, lang=self.tree_lang).lower())
        self.parent_lookup = {self.get_label(s, lang=self.tree_lang): s for s in concepts}

        inserted_nodes = {}

        # Iterative stack-based DFS to insert items
        # Stack elements: (parent_id, concept_uri, path_set, is_root)
        # We push roots/children in reverse alphabetical order to pop and process in alphabetical order
        stack = []
        for r in reversed(roots):
            stack.append(("", r, set(), True))
            
        while stack:
            parent_id, concept_uri, path_set, is_root = stack.pop()
            
            if concept_uri in path_set:
                continue
                
            lbl = self.get_label(concept_uri, lang=self.tree_lang)
            if filter_txt and filter_txt not in lbl.lower():
                continue
                
            u_str = str(concept_uri)
            is_open = u_str in expanded_uris
            prefix = "📂 " if is_root else " └─ "
            
            node_id = self.tree.insert(parent_id, "end", text=f"{prefix}{lbl}", values=(u_str,), open=is_open)
            inserted_nodes[u_str] = node_id
            
            kids = sorted(
                [(c, self.get_label(c, lang=self.tree_lang)) for c in self.mgr.get_child_concepts(concept_uri)],
                key=lambda x: x[1].lower(),
                reverse=True
            )
            
            new_path_set = path_set | {concept_uri}
            for child_uri, _ in kids:
                stack.append((node_id, child_uri, new_path_set, False))

        if selected_uri and selected_uri in inserted_nodes:
            target_id = inserted_nodes[selected_uri]
            self.tree.selection_set(target_id)
            self.tree.see(target_id)

    def run_create_vocab(self):
        path = filedialog.asksaveasfilename(title="Create New Vocabulary File", defaultextension=".ttl", filetypes=[("Turtle Files", "*.ttl")])
        if not path: return
        name = os.path.basename(path).replace(".ttl", "")
        
        default_ns = f"http://vocabs.bcdh.uni-bonn.de/{name}/"
        dialog = ctk.CTkInputDialog(text=f"Specify custom URI base namespace for the vocabulary:\n(e.g., 3dvocabular or http://my-uri.org)\n(Default suggestion: {default_ns})", title="Custom Namespace Definition")
        input_ns = dialog.get_input()
        
        if not input_ns or input_ns.strip() == "": input_ns = default_ns
        else:
            input_ns = input_ns.strip()
            if not (input_ns.startswith("http://") or input_ns.startswith("https://")):
                input_ns = "http://" + input_ns
            if not input_ns.endswith(("/", "#")): input_ns += "/"

        self.mgr.create_new_vocabulary(path, input_ns, name)
        self.scheme_uri = self.mgr.scheme_uri
        self.current_file_path = path

        self.clear_all_editor_fields()
        self.load_data(path)

    def run_prepare_new_concept(self):
        if not self.current_file_path:
            messagebox.showwarning("New Concept", "Please import or create a vocabulary file before generating new concepts!")
            return
            
        self.rebuild_form_grid()
        base_ns = self.get_clean_namespace()
        if "uri" in self.entries and self.entries["uri"].winfo_exists():
            self.entries["uri"].configure(state="normal")
            self.entries["uri"].delete(0, "end")
            self.entries["uri"].insert(0, f"{base_ns}concept_{uuid.uuid4().hex[:8]}")
            self.entries["uri"].configure(state="disabled")
            
        for f in ["match_wiki", "match_aat", "match_gnd"]: 
            if f in self.entries and self.entries[f].winfo_exists(): self.entries[f].delete(0, "end")
            
        for widget in self.lang_entries.values(): 
            if widget.winfo_exists(): widget.delete(0, "end")

        for widget in self.def_entries.values(): 
            if widget.winfo_exists(): widget.delete(0, "end")
            
        for frame in self.alt_label_frames.values():
            if frame.winfo_exists():
                for child in frame.winfo_children(): child.destroy()
                
        self.alt_label_widgets = {lang: [] for lang in self.all_possible_languages}
        if hasattr(self, "first_parent_widget") and self.first_parent_widget.winfo_exists():
            self.first_parent_widget.delete(0, "end")
        if hasattr(self, "parent_frame") and self.parent_frame.winfo_exists():
            for child in self.parent_frame.winfo_children():
                child.destroy()
        self.parent_widgets = [self.first_parent_widget] if hasattr(self, "first_parent_widget") else []
        self.log("✨ New concept initialization layout ready.")

    def run_delete_concept(self):
        if "uri" not in self.entries or not self.entries["uri"].winfo_exists(): return
        uri_str = self.entries["uri"].get()
        if not uri_str: return
        uri = URIRef(uri_str)
        
        children = self.mgr.get_child_concepts(uri)
        if children:
            ans = messagebox.askyesnocancel(
                "Delete Hierarchy?",
                f"The concept '{self.get_label(uri, lang=self.tree_lang)}' has {len(children)} sub-concepts.\n\n"
                "YES: Delete the entire branch recursively (all child concepts).\n"
                "NO: Delete only this single concept and move child concepts up.\n"
                "CANCEL: Abort operation."
            )
            if ans is None: return
            elif ans is True: 
                self.mgr.delete_concept_recursive(uri)
                self.log("🗑️ Entire sub-hierarchy deleted recursively.")
            else: 
                self.mgr.delete_concept_single(uri)
                self.log("🗑️ Core concept removed. Children re-allocated to vocabulary roots.")
        else:
            self.mgr.delete_concept_single(uri)
            self.log("🗑️ Concept deleted.")

        self.rebuild_form_grid()
        self.clear_all_editor_fields()
        self.update_tree_ui()

    def run_import_facet(self):
        if not self.current_file_path:
            messagebox.showwarning("Facet Import", "Please open a target main vocabulary file first!")
            return
        path = filedialog.askopenfilename(title="Select Facet File to Import", filetypes=[("Turtle Files", "*.ttl"), ("All Files", "*.*")])
        if not path: return
        try:
            facet_g = Graph()
            facet_g.parse(path, format="turtle")
            
            align_choice = messagebox.askyesno(
                "URI Alignment Schema Configuration",
                "Do you want to adapt all imported data to the current vocabulary's base namespace and generate completely new anonymous schema URIs (concept_xxxx)?\n\n"
                "YES: Convert namespace and mint fresh randomized URIs.\n"
                "NO: Retain original foreign namespaces and stable URIs intact."
            )
            self.import_align_uris = align_choice
            self.open_facet_parent_selector(facet_g)
        except Exception as e: messagebox.showerror("Import Error", f"Failed to parse source turtle file:\n{e}")

    def open_facet_parent_selector(self, facet_g):
        selector = ctk.CTkToplevel(self.root)
        selector.title("Facet Parent Assignment Mapping")
        selector.geometry("550x550")
        selector.lift()
        selector.attributes("-topmost", True)
        
        lbl = ctk.CTkLabel(selector, text="Select the concept node under which the imported facet roots should be appended:", font=("Arial", 12, "bold"), wraplength=500)
        lbl.pack(pady=10)
        
        txt_search_parent = ctk.CTkEntry(selector, placeholder_text="Type to filter parent concepts...", font=("Arial", 12))
        txt_search_parent.pack(fill="x", padx=20, pady=5)
        
        scroll_frame = ctk.CTkScrollableFrame(selector)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        concepts = sorted(list(self.mgr.get_concepts()), key=lambda x: self.get_label(x, lang=self.tree_lang).lower())
        buttons_map = []
        
        btn_top = ctk.CTkButton(scroll_frame, text="[ Append as independent Top-Concept / Root elements ]", fg_color="#4f4f4f", anchor="w", command=lambda: self.process_facet_alignment(facet_g, None, selector))
        btn_top.pack(fill="x", pady=4, padx=5)

        def filter_parents(e):
            query = txt_search_parent.get().lower().strip()
            for btn, lbl_t in buttons_map:
                if query in lbl_t.lower(): btn.pack(fill="x", pady=2, padx=5)
                else: btn.pack_forget()

        txt_search_parent.bind("<KeyRelease>", filter_parents)

        for c in concepts:
            lbl_text = self.get_label(c, lang=self.tree_lang)
            btn = ctk.CTkButton(scroll_frame, text=lbl_text, fg_color="transparent", text_color=("black", "white"), hover_color=("#dbdbdb", "#2b2b2b"), anchor="w",
                                command=lambda targeted_concept=c: self.process_facet_alignment(facet_g, targeted_concept, selector))
            btn.pack(fill="x", pady=2, padx=5)
            buttons_map.append((btn, lbl_text))

    def process_facet_alignment(self, facet_g, parent_uri, window):
        window.destroy()
        current_ns = self.get_clean_namespace()
        count = self.mgr.import_facet(facet_g, parent_uri, self.import_align_uris)
        self.update_tree_ui()
        self.log(f"📥 Facet processing completed. Aligned {count} items onto namespace base: '{current_ns}'.")

    def run_export_facet(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("Facet Export Options", "Please select a node inside the hierarchy tree to trigger the export pipeline!")
            return
        
        root_uri = URIRef(self.tree.item(selected_item[0])["values"][0])
        ans = messagebox.askyesnocancel(
            "Export Options",
            f"Do you want to export the entire sub-hierarchy of '{self.get_label(root_uri, lang=self.tree_lang)}'?\n\n"
            "YES: Export this concept along with ALL its sub-concepts.\n"
            "NO: Export ONLY this single concept entity.\n"
            "CANCEL: Abort export process."
        )
        if ans is None: return
        
        path = filedialog.asksaveasfilename(title="Save Exported Facet", defaultextension=".ttl", filetypes=[("Turtle Files", "*.ttl")])
        if not path: return
        
        try:
            count = self.mgr.export_facet(root_uri, ans is True, path)
            self.log(f"📤 Export generated successfully ({count} concepts saved): {os.path.basename(path)}")
        except Exception as e: messagebox.showerror("Export Error", f"Failed to serialize file onto storage target:\n{e}")

    def run_health_check(self):
        self.log("🏥 Running rapid semantic health scan...")
        orphans = [self.get_label(s, lang=self.tree_lang) for s in self.mgr.run_health_check()]
        if orphans: self.log(f"🚫 Stale orphan nodes detected: {', '.join(orphans)}")
        else: self.log("✅ No orphan nodes. Validation clear.")

    def run_fix_labels(self):
        self.log("🛠_ Re-indexing and repairing graph strings...")
        repaired_count = self.mgr.run_fix_labels()
        self.update_tree_ui()
        self.log(f"✅ Success. Repaired {repaired_count} concept resources.")


if __name__ == "__main__":
    try:
        root = ctk.CTk()
        app = HECTOREditor(root)
        root.mainloop()
    except Exception as boot_exception:
        print(f"\nCRITICAL BOOT ERROR:\n{traceback.format_exc()}")
        input("\nPress ENTER to terminate application workspace...")