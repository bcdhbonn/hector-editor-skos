import json
import os
import uuid
import urllib.request
import urllib.parse
from tkinter import filedialog, messagebox, ttk
import tkinter as tk  # Native Tkinter components utilized for deterministic layout constraints
import customtkinter as ctk
from rdflib import Graph, Literal, RDF, SKOS, URIRef

# Global persistent configuration registry path
CONFIG_FILE = "hector_config.json"


class HECTOREditor:
    """
    Main controller class for the HECTOR-Editor Pro (Integrated Authority Edition).
    Manages semantic graph lifecycles via RDFLib, orchestrates external asynchronous
    Wikidata API queries, and maintains a unified responsive GUI architecture.
    """

    def __init__(self, root):
        self.root = root
        self.root.title("HECTOR-Editor")
        self.root.geometry("1350x920")

        # Core semantic triplestore graph structures and internal runtime states
        self.g = Graph()
        self.current_file_path = ""
        self.scheme_uri = URIRef("http://example.org/scheme")
        self.parent_lookup = {}        # Maps human-readable skos:prefLabels to explicit URIs
        self.delete_target_uri = None  # Tracks state context for secure two-step tree deletion
        self.search_popup = None
        self.wiki_window = None
        self.lang_popup = None

        # Multilingual ISO 639-1 language parameter registry
        self.all_possible_languages = ["en", "de", "fr", "es", "it", "la", "grc"]
        self.active_languages = ["en", "de"] 
        
        # Component caches mapping dynamic multilingual UI objects to runtime handlers
        self.lang_entries = {}      # Maps language codes to primary prefLabel ctk.CTkEntry widgets
        self.alt_label_frames = {}  # Maps language codes to child tk.Frame structures containing synonyms
        self.alt_label_widgets = {} # Maps language codes to active arrays of alternate label entry points

        self.entries = {}  # Initialize the entry registry properly before building components

        # Initialize operational core subroutines
        self.load_config()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_app)
        self.build_ui()
        self.setup_styles()

        # UI BUGFIX: Clear fields ONLY after the UI components have been completely mapped into existence
        self.clear_all_editor_fields()
        if hasattr(self, 'remembered_path') and self.remembered_path and os.path.exists(self.remembered_path):
            self.load_data(self.remembered_path)

    def build_ui(self):
        """
        Constructs the high-level structural window geometry grid mapping.
        Allocates screen real estate into Left Workspace (Navigation/Search) and Right Workspace (Editor).
        """
        # Enforce explicit structural scaling weights for high-resolution responsive layout adaptions
        self.root.grid_columnconfigure(0, weight=1, minsize=420)
        self.root.grid_columnconfigure(1, weight=2, minsize=750)
        self.root.grid_rowconfigure(0, weight=1)

        # =========================================================================
        # ---- LEFT WORKSPACE PANEL: GRAPH NAVIGATION TREE & INLINE FILTERING -----
        # =========================================================================
        self.left_frame = ctk.CTkFrame(self.root, corner_radius=15)
        self.left_frame.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")
        self.left_frame.grid_columnconfigure(0, weight=1)
        self.left_frame.grid_rowconfigure(6, weight=1) # Allocates remaining vertical space to the hierarchy tree

        # App Identity Block Container
        self.header_frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, padx=15, pady=(15, 5), sticky="ew")
        self.header_frame.grid_columnconfigure(0, weight=1)

        self.lbl_file_header = ctk.CTkLabel(self.header_frame, text="🏛️ HECTOR-EDITOR", font=("Arial", 12))
        self.lbl_file_header.grid(row=0, column=0, sticky="w")

        self.switch_theme = ctk.CTkSwitch(self.header_frame, text="Dark Mode", command=self.toggle_theme, font=("Arial", 12))
        self.switch_theme.grid(row=0, column=1, sticky="e")
        if ctk.get_appearance_mode() == "Dark":
            self.switch_theme.select()

        # File System Initialization Triggers
        self.btn_open = ctk.CTkButton(self.left_frame, text="Import / Open Vocabulary (.ttl)", command=self.open_file_dialog, fg_color="#2fa572", hover_color="#107c41", font=("Arial", 12))
        self.btn_open.grid(row=1, column=0, padx=15, pady=5, sticky="ew")

        self.lbl_status = ctk.CTkLabel(self.left_frame, text="No vocabulary file loaded", text_color="gray", font=("Arial", 12))
        self.lbl_status.grid(row=2, column=0, padx=15, pady=(0, 15), sticky="w")

        self.lbl_search_header = ctk.CTkLabel(self.left_frame, text="🔍 SEARCH & HIERARCHY", font=("Arial", 12))
        self.lbl_search_header.grid(row=3, column=0, padx=15, pady=(5, 0), sticky="w")

        # Interactive String Interception Filter Entry
        self.txt_search = ctk.CTkEntry(self.left_frame, placeholder_text="Type to filter hierarchy...", font=("Arial", 12))
        self.txt_search.grid(row=4, column=0, padx=15, pady=5, sticky="ew")
        self.txt_search.bind("<KeyRelease>", lambda e: self.update_tree_ui())

        # Native Treeview Component Integration for Advanced SKOS Hierarchy Rendering
        self.tree_container = ctk.CTkFrame(self.left_frame)
        self.tree_container.grid(row=6, column=0, padx=15, pady=15, sticky="nsew")
        self.tree_container.grid_columnconfigure(0, weight=1)
        self.tree_container.grid_rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(self.tree_container, show="tree", selectmode="browse")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_node_click)

        self.scrollbar = ttk.Scrollbar(self.tree_container, orient="vertical", command=self.tree.yview)
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=self.scrollbar.set)

        # =========================================================================
        # ---- RIGHT WORKSPACE PANEL: DATA SERIALIZATION FORM & API SUB-SYSTEMS ---
        # =========================================================================
        self.right_frame = ctk.CTkScrollableFrame(self.root, corner_radius=15)
        self.right_frame.grid(row=0, column=1, padx=15, pady=15, sticky="nsew")
        self.right_frame.grid_columnconfigure(0, weight=1)

        # Section Handler: ConceptScheme Initializer
        self.lbl_new_v = ctk.CTkLabel(self.right_frame, text="🆕 CREATE NEW VOCABULARY", font=("Arial", 12))
        self.lbl_new_v.grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")

        self.vocab_init_frame = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        self.vocab_init_frame.grid(row=1, column=0, padx=15, pady=5, sticky="ew")
        self.vocab_init_frame.grid_columnconfigure(0, weight=1)

        self.ent_new_vocab = ctk.CTkEntry(self.vocab_init_frame, placeholder_text="vocabulary_name.ttl", height=28, font=("Arial", 12))
        self.ent_new_vocab.grid(row=0, column=0, padx=(0, 10), sticky="ew")

        self.btn_create_v = ctk.CTkButton(self.vocab_init_frame, text="Initialize Schema", width=140, height=28, font=("Arial", 12), command=self.run_create_vocab)
        self.btn_create_v.grid(row=0, column=1, sticky="e")

        # Section Handler: Concept Modificator (CRUD Controls)
        self.lbl_editor = ctk.CTkLabel(self.right_frame, text="✏️ CONCEPT EDITOR", font=("Arial", 12))
        self.lbl_editor.grid(row=2, column=0, padx=15, pady=(15, 5), sticky="w")

        self.crud_btn_frame = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        self.crud_btn_frame.grid(row=3, column=0, padx=15, pady=5, sticky="ew")
        self.crud_btn_frame.grid_columnconfigure((0, 1), weight=1)

        self.btn_new_c = ctk.CTkButton(self.crud_btn_frame, text="➕ Create New Concept", fg_color="#1f538d", height=30, font=("Arial", 12), command=self.run_prepare_new_concept)
        self.btn_new_c.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.btn_del_c = ctk.CTkButton(self.crud_btn_frame, text="🗑️ Delete Concept", fg_color="#a83232", hover_color="#7a2222", height=30, font=("Arial", 12), command=self.run_delete_concept)
        self.btn_del_c.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        # FORM MATRIX CONTAINER STABILIZATION:
        self.form_frame = ctk.CTkFrame(self.right_frame, corner_radius=10, border_width=1)
        self.form_frame.grid(row=4, column=0, padx=15, pady=10, sticky="ew")
        self.form_frame.grid_columnconfigure(1, weight=1)

        self.rebuild_form_grid()

        # Database Pipeline Serialization Trigger
        self.btn_save = ctk.CTkButton(self.right_frame, text="💾 Commit Changes / Save Concept", fg_color="#2fa572", hover_color="#107c41", height=35, font=("Arial", 12), command=self.on_save)
        self.btn_save.grid(row=5, column=0, padx=15, pady=10, sticky="ew")

        # Section Handler: Graph Validation Diagnostics
        self.lbl_tools = ctk.CTkLabel(self.right_frame, text="⚙️ DATA QUALITY ASSURANCE", font=("Arial", 12))
        self.lbl_tools.grid(row=6, column=0, padx=15, pady=(15, 5), sticky="w")

        self.tools_btn_frame = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        self.tools_btn_frame.grid(row=7, column=0, padx=15, pady=5, sticky="ew")
        self.tools_btn_frame.grid_columnconfigure((0, 1), weight=1)

        self.btn_t_fix = ctk.CTkButton(self.tools_btn_frame, text="🛠️ Repair Missing URI Labels", height=28, font=("Arial", 12), command=self.run_fix_labels)
        self.btn_t_fix.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.btn_t_check = ctk.CTkButton(self.tools_btn_frame, text="🏥 Health Check", height=28, font=("Arial", 12), command=self.run_health_check)
        self.btn_t_check.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        self.out_tools = ctk.CTkTextbox(self.right_frame, height=100, fg_color="black", text_color="lightgreen", font=("Consolas", 12))
        self.out_tools.grid(row=8, column=0, padx=15, pady=(5, 15), sticky="ew")

    def toggle_theme(self):
        """Coordinates standard system look and feel parameter theme swapping safely."""
        if self.switch_theme.get() == 1:
            ctk.set_appearance_mode("Dark")
        else:
            ctk.set_appearance_mode("Light")
            
        self.setup_styles()
        self.rebuild_form_grid()

    def rebuild_form_grid(self):
        """Forces a razor-sharp tabular layout with aligned columns and zero vertical bloating"""
        # LIFECYCLE PROTECTOR: Prevent state exceptions against cleared layout objects
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

        for widget in self.form_frame.winfo_children():
            widget.destroy()

        is_dark = (ctk.get_appearance_mode() == "Dark")
        bg_color = "#2b2b2b" if is_dark else "#eaeaea"
        text_color = "white" if is_dark else "black"

        # Apply synchronized coloring context directly onto the CustomTkinter frame
        self.form_frame.configure(fg_color=bg_color)

        # GRID STRUCTURAL ALIGNMENT COLUMNS PROPORTIONS STABILIZATION:
        self.form_frame.grid_columnconfigure(0, weight=0, minsize=180)
        self.form_frame.grid_columnconfigure(1, weight=1)
        self.form_frame.grid_columnconfigure(2, weight=0, minsize=170)

        for r in range(50):
            self.form_frame.grid_rowconfigure(r, weight=0, minsize=0)

        current_row = 0

        if not self.current_file_path:
            return

        # 1. Technical URI Field
        tk.Label(self.form_frame, text="URI (Read-only):", font=("Arial", 12), bg=bg_color, fg=text_color, anchor="w").grid(row=current_row, column=0, padx=(15, 5), pady=3, sticky="w")
        self.entries["uri"] = ctk.CTkEntry(self.form_frame, height=28, font=("Arial", 12))
        self.entries["uri"].grid(row=current_row, column=1, columnspan=2, padx=(5, 15), pady=(15, 3), sticky="ew")
        if "uri" in cached_vals:
            self.entries["uri"].insert(0, cached_vals["uri"])
        self.entries["uri"].configure(state="disabled")
        current_row += 1

        # 2. CENTRAL LANGUAGE HEADER (DYNAMIC THEME COMPLIANT)
        tk.Label(self.form_frame, text="Languages:", font=("Arial", 12), bg=bg_color, fg=text_color, anchor="w").grid(row=current_row, column=0, padx=(15, 5), pady=4, sticky="w")
        display_text = f"Selected: {', '.join([l.upper() for l in self.active_languages])}"
        
        if is_dark:
            dropdown_btn_bg = "#4f4f4f"
            dropdown_btn_hover = "#3a3a3a"
            dropdown_btn_text = "white"
        else:
            dropdown_btn_bg = "#d1d1d1"
            dropdown_btn_hover = "#c1c1c1"
            dropdown_btn_text = "black"
            
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

        # 3. VERTICAL MULTI-LINGUAL FIELDS
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

        # 4. Definition Field
        tk.Label(self.form_frame, text="skos:definition:", font=("Arial", 12), bg=bg_color, fg=text_color, anchor="w").grid(row=current_row, column=0, padx=(15, 5), pady=4, sticky="w")
        self.entries["def"] = ctk.CTkEntry(self.form_frame, height=28, font=("Arial", 12))
        self.entries["def"].grid(row=current_row, column=1, columnspan=2, padx=(5, 15), pady=4, sticky="ew")
        if "def" in cached_vals: self.entries["def"].insert(0, cached_vals["def"])
        current_row += 1

        # 5. Parent Link Allocation Field
        tk.Label(self.form_frame, text="Parent:", font=("Arial", 12), bg=bg_color, fg=text_color, anchor="w").grid(row=current_row, column=0, padx=(15, 5), pady=4, sticky="w")
        self.entries["broad"] = ctk.CTkEntry(self.form_frame, height=28, font=("Arial", 12), placeholder_text="Type to find parent...")
        self.entries["broad"].grid(row=current_row, column=1, padx=(5, 5), pady=4, sticky="ew")
        self.entries["broad"].bind("<KeyRelease>", self.handle_entry_search)
        if "broad" in cached_vals: self.entries["broad"].insert(0, cached_vals["broad"])

        self.btn_set_top = ctk.CTkButton(self.form_frame, text="Make Top Concept", width=160, height=26, fg_color="#6e6e6e", hover_color="#525252", font=("Arial", 12), command=self.clear_parent_to_top)
        self.btn_set_top.grid(row=current_row, column=2, padx=(5, 15), pady=4, sticky="e")
        current_row += 1

        # 6. Alignment Reference Matches
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
        """Appends an alternative alias expression entry row safely targeting designated language subsets."""
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
        """Disposes of alternate synonym fields and forces a layout geometric refresh cycle."""
        if entry_widget in self.alt_label_widgets[lang]: 
            self.alt_label_widgets[lang].remove(entry_widget)
        row_frame.destroy()
        self.form_frame.update_idletasks()

    def toggle_language_dropdown_popup(self):
        """Generates an explicit boundary-bound multi-select dropdown popover layer for managing display languages."""
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
        """Safely disposes of active language selector popup layers."""
        if self.lang_popup: self.lang_popup.destroy(); self.lang_popup = None

    def on_checkbox_toggled(self):
        """Monitors multi-selection alterations to structural language visibility parameters and stews grid redraws."""
        self.active_languages = [lang for lang, var in self.checkbox_vars.items() if var.get()]
        display_text = f"Selected: {', '.join([l.upper() for l in self.active_languages])}"
        self.btn_lang_dropdown.configure(text=f"{display_text}  ▼")
        self.rebuild_form_grid()

    def run_register_new_language_to_pool(self):
        """Validates and pushes a customized ISO code label straight into operational selection arrays."""
        code = self.ent_new_lang_code.get().strip().lower()
        if not code or code in self.all_possible_languages: return
        self.all_possible_languages.append(code)
        self.active_languages.append(code)
        self.close_language_dropdown_popup()
        self.rebuild_form_grid()

    def fetch_from_wikidata(self):
        """Dispatches external HTTP queries to find matching entities to automate mapping."""
        search_term = ""
        search_lang = "en"
        
        if "en" in self.lang_entries and self.lang_entries["en"].get().strip():
            search_term = self.lang_entries["en"].get().strip()
            search_lang = "en"
        else:
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
        """Builds an isolated selection popover showing potential target concept entities layout records."""
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
        """Unpacks precise data components out from the chosen reference node payload structure."""
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
                        if val:
                            self.lang_entries[lang].insert(0, val)
                        elif lang == "en" and not en_label:
                            global_fallback = next(iter(labels.values()), {}).get("value", "")
                            self.lang_entries["en"].insert(0, global_fallback)

                descriptions = entity.get("descriptions", {})
                en_desc = descriptions.get("en", {}).get("value", "")
                fallback_desc = en_desc if en_desc else next(iter(descriptions.values()), {}).get("value", "")
                if fallback_desc and "def" in self.entries and self.entries["def"].winfo_exists():
                    self.entries["def"].delete(0, "end")
                    self.entries["def"].insert(0, fallback_desc)

                if "match_wiki" in self.entries and self.entries["match_wiki"].winfo_exists():
                    self.entries["match_wiki"].delete(0, "end")
                    self.entries["match_wiki"].insert(0, wiki_uri)

                claims = entity.get("claims", {})
                
                # Getty AAT Pipeline
                if "match_aat" in self.entries and self.entries["match_aat"].winfo_exists():
                    self.entries["match_aat"].delete(0, "end")
                    if "P1014" in claims:
                        aat_id = claims["P1014"][0]["mainsnak"]["datavalue"]["value"]
                        self.entries["match_aat"].insert(0, f"http://vocab.getty.edu/aat/{aat_id}")
                        self.log(f"🏛️ Resolved Getty AAT URI: {aat_id}")

                # Integrated GND Record Pipeline
                if "match_gnd" in self.entries and self.entries["match_gnd"].winfo_exists():
                    self.entries["match_gnd"].delete(0, "end")
                    if "P227" in claims:
                        gnd_id = claims["P227"][0]["mainsnak"]["datavalue"]["value"]
                        self.entries["match_gnd"].insert(0, f"https://d-nb.info/gnd/{gnd_id}")
                        self.log(f"🇩🇪 Resolved GND Control URI: {gnd_id}")

                self.log(f"✅ Context extraction finished for {q_id}.")
        except Exception as e: self.log(f"❌ Claim parsing disruption: {e}")

    def on_save(self):
        """Serializes local input variables out to highly compliant SKOS semantic triples syntax blocks."""
        if "uri" not in self.entries or not self.entries["uri"].winfo_exists(): return
        uri_str = self.entries["uri"].get()
        if not uri_str or not self.current_file_path: return
        uri = URIRef(uri_str)

        for p in [SKOS.prefLabel, SKOS.altLabel, SKOS.definition, SKOS.broader, SKOS.topConceptOf, SKOS.exactMatch]: 
            self.g.remove((uri, p, None))

        self.g.add((uri, RDF.type, SKOS.Concept))

        for lang, widget in self.lang_entries.items():
            if widget.winfo_exists():
                text_val = widget.get().strip()
                if text_val: self.g.add((uri, SKOS.prefLabel, Literal(text_val, lang=lang)))

        for lang, entries_list in self.alt_label_widgets.items():
            for ent_widget in entries_list:
                if ent_widget.winfo_exists():
                    alt_val = ent_widget.get().strip()
                    if alt_val: self.g.add((uri, SKOS.altLabel, Literal(alt_val, lang=lang)))

        if "def" in self.entries and self.entries["def"].winfo_exists() and self.entries["def"].get().strip(): 
            self.g.add((uri, SKOS.definition, Literal(self.entries["def"].get().strip())))
        
        if "match_wiki" in self.entries and self.entries["match_wiki"].winfo_exists() and self.entries["match_wiki"].get().strip(): 
            self.g.add((uri, SKOS.exactMatch, URIRef(self.entries["match_wiki"].get().strip())))
        if "match_aat" in self.entries and self.entries["match_aat"].winfo_exists() and self.entries["match_aat"].get().strip(): 
            self.g.add((uri, SKOS.exactMatch, URIRef(self.entries["match_aat"].get().strip())))
        if "match_gnd" in self.entries and self.entries["match_gnd"].winfo_exists() and self.entries["match_gnd"].get().strip(): 
            self.g.add((uri, SKOS.exactMatch, URIRef(self.entries["match_gnd"].get().strip())))

        broad_val = self.entries["broad"].get().strip() if ("broad" in self.entries and self.entries["broad"].winfo_exists()) else ""
        if broad_val and broad_val in self.parent_lookup: 
            self.g.add((uri, SKOS.broader, self.parent_lookup[broad_val]))
        else: 
            self.g.add((uri, SKOS.topConceptOf, self.scheme_uri))
            self.g.add((self.scheme_uri, SKOS.hasTopConcept, uri))

        self.g.serialize(destination=self.current_file_path, format="turtle")
        self.update_tree_ui()
        self.log(f"💾 Graph synced to file: {self.get_label(uri)}")

    def on_tree_node_click(self, event):
        """Catches visual component node hit events to hydra metadata text field boxes."""
        selected_item = self.tree.selection()
        if not selected_item: return
        uri = URIRef(self.tree.item(selected_item[0])["values"][0])
        
        self.rebuild_form_grid()
        self.clear_all_editor_fields()
        
        if "uri" in self.entries and self.entries["uri"].winfo_exists():
            self.entries["uri"].configure(state="normal")
            self.entries["uri"].insert(0, str(uri))
            self.entries["uri"].configure(state="disabled")
        
        for literal in self.g.objects(uri, SKOS.prefLabel):
            if hasattr(literal, "language") and literal.language:
                lang_code = literal.language
                if lang_code not in self.all_possible_languages: self.all_possible_languages.append(lang_code)
                if lang_code not in self.active_languages:
                    self.active_languages.append(lang_code)
                    self.rebuild_form_grid()
                if lang_code in self.lang_entries and self.lang_entries[lang_code].winfo_exists():
                    self.lang_entries[lang_code].delete(0, "end")
                    self.lang_entries[lang_code].insert(0, str(literal))

        for literal in self.g.objects(uri, SKOS.altLabel):
            if hasattr(literal, "language") and literal.language:
                lang_code = literal.language
                if lang_code not in self.all_possible_languages: self.all_possible_languages.append(lang_code)
                if lang_code not in self.active_languages:
                    self.active_languages.append(lang_code)
                    self.rebuild_form_grid()
                self.add_alt_label_row(lang_code, initial_text=str(literal))

        if hasattr(self, "btn_lang_dropdown") and self.btn_lang_dropdown.winfo_exists():
            display_text = f"Selected: {', '.join([l.upper() for l in self.active_languages])}"
            self.btn_lang_dropdown.configure(text=f"{display_text}  ▼")

        if "def" in self.entries and self.entries["def"].winfo_exists():
            self.entries["def"].insert(0, next((str(d) for d in self.g.objects(uri, SKOS.definition)), ""))
        if "broad" in self.entries and self.entries["broad"].winfo_exists():
            p = list(self.g.objects(uri, SKOS.broader))
            if p: self.entries["broad"].insert(0, self.get_label(p[0]))
        
        matches = list(self.g.objects(uri, SKOS.exactMatch))
        for m in matches:
            m_str = str(m)
            if "wikidata.org" in m_str and "match_wiki" in self.entries and self.entries["match_wiki"].winfo_exists(): 
                self.entries["match_wiki"].insert(0, m_str)
            elif "getty.edu" in m_str and "match_aat" in self.entries and self.entries["match_aat"].winfo_exists(): 
                self.entries["match_aat"].insert(0, m_str)
            elif "d-nb.info" in m_str and "match_gnd" in self.entries and self.entries["match_gnd"].winfo_exists(): 
                self.entries["match_gnd"].insert(0, m_str)

    def clear_all_editor_fields(self):
        """Flushes storage structures to establish clean blank state controls values."""
        if "uri" in self.entries and self.entries["uri"].winfo_exists():
            self.entries["uri"].configure(state="normal")
            self.entries["uri"].delete(0, "end")
            self.entries["uri"].configure(state="disabled")
            
        for widget in self.lang_entries.values(): 
            if widget.winfo_exists(): widget.delete(0, "end")
            
        for frame in self.alt_label_frames.values():
            if frame.winfo_exists():
                for child in frame.winfo_children(): child.destroy()
                
        self.alt_label_widgets = {lang: [] for lang in self.all_possible_languages}
        for field in ["def", "broad", "match_wiki", "match_aat", "match_gnd"]: 
            if field in self.entries and self.entries[field].winfo_exists():
                self.entries[field].delete(0, "end")

    def handle_entry_search(self, event):
        """Renders asynchronous autocompletion options dropdown overlay panes."""
        if "broad" not in self.entries or not self.entries["broad"].winfo_exists(): return
        val = self.entries["broad"].get().lower().strip()
        if self.search_popup: self.search_popup.destroy(); self.search_popup = None
        if not val or not self.parent_lookup: return
        matches = [item for item in self.parent_lookup.keys() if val in item.lower()]
        if not matches: return
        x = self.entries["broad"].winfo_rootx()
        y = self.entries["broad"].winfo_rooty() + self.entries["broad"].winfo_height()
        self.search_popup = ctk.CTkToplevel(self.root)
        self.search_popup.wm_overrideredirect(True)
        self.search_popup.wm_geometry(f"{self.entries['broad'].winfo_width()}x150+{x}+{y}")
        scroll_box = ctk.CTkScrollableFrame(self.search_popup, label_text="Matches found:")
        scroll_box.pack(fill="both", expand=True)
        for match in matches[:30]:
            btn = ctk.CTkButton(scroll_box, text=match, anchor="w", fg_color="transparent", text_color=("black", "white"), hover_color=("#dbdbdb", "#2b2b2b"), height=24, font=("Arial", 12), command=lambda m=match: self.select_parent_from_popup(m))
            btn.pack(fill="x")

    def select_parent_from_popup(self, match_value):
        """Applies chosen inline metadata selection variable directly onto field text strings."""
        if "broad" in self.entries and self.entries["broad"].winfo_exists():
            self.entries["broad"].delete(0, "end")
            self.entries["broad"].insert(0, match_value)
        if self.search_popup: self.search_popup.destroy(); self.search_popup = None

    def clear_parent_to_top(self):
        """Purges contextual link parameters to bind the element to the schema collection root."""
        if "broad" in self.entries and self.entries["broad"].winfo_exists():
            self.entries["broad"].delete(0, "end")
        if self.search_popup: self.search_popup.destroy(); self.search_popup = None

    def load_config(self):
        """Loads persistent session parameters from the project workspace configurations path."""
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
        """Saves session parameters inside JSON mapping tracking tracks."""
        cfg = {"last_path": self.current_file_path, "theme": ctk.get_appearance_mode()}
        try:
            with open(CONFIG_FILE, "w") as f: json.dump(cfg, f, indent=4)
        except: pass

    def setup_styles(self):
        """Applies global style specifications ensuring predictable visualization variables."""
        style = ttk.Style()
        is_dark = ctk.get_appearance_mode() == "Dark"
        bg_color = "#2a2a2a" if is_dark else "#f0f0f0"
        fg_color = "#ffffff" if is_dark else "#000000"
        select_color = "#1f538d" if is_dark else "#add8e6"
        style.theme_use("default")
        style.configure("Treeview", background=bg_color, foreground=fg_color, fieldbackground=bg_color, rowheight=26, font=("Arial", 12))
        style.map("Treeview", background=[("selected", select_color)])

    def on_close_app(self):
        """Ensures secure structural disposal of open window resources across quit tasks."""
        if self.search_popup: self.search_popup.destroy()
        if self.wiki_window: self.wiki_window.destroy()
        if self.lang_popup: self.lang_popup.destroy()
        self.save_config()
        self.root.destroy()

    def open_file_dialog(self):
        """Öffnet den System-Dialog zum Importieren einer Turtle-Datei."""
        path = filedialog.askopenfilename(
            title="Vokabular öffnen",
            filetypes=[("Turtle Files", "*.ttl"), ("All Files", "*.*")]
        )
        if path:
            self.load_data(path)

    def log(self, message):
        """Routet Systemnachrichten in das Diagnose-Panel und die Konsole."""
        print(message)
        if hasattr(self, 'out_tools') and self.out_tools.winfo_exists():
            self.out_tools.insert("end", message + "\n")
            self.out_tools.see("end")  # Auto-Scroll nach unten

    def load_data(self, path):
        """Reads targeted data inputs, compiling strings straight into internal RDF graphs."""
        self.current_file_path = path
        self.g = Graph()
        try:
            self.g.parse(self.current_file_path, format="turtle")
            schemes = list(self.g.subjects(RDF.type, SKOS.ConceptScheme))
            if schemes: self.scheme_uri = schemes[0]
            self.delete_target_uri = None
            self.lbl_status.configure(text=os.path.basename(path))
            
            # Rebuild grid context dynamically to clean layout pipelines safely
            self.rebuild_form_grid()
            self.clear_all_editor_fields()
            self.update_tree_ui()
            self.log(f"🏛 *Vocabulary imported safely:* {os.path.basename(path)}")
        except Exception as e: messagebox.showerror("IO Error", f"Could not load graph file:\n{e}")

    def get_label(self, uri):
        """Utility transformer unpacking machine-readable URIs out to intuitive local human label strings."""
        labels = list(self.g.objects(uri, SKOS.prefLabel))
        for lang in self.all_possible_languages:
            for l in labels:
                if l.language == lang: return str(l)
        if labels: return str(labels[0])
        return str(uri).split("#")[-1] if "#" in str(uri) else str(uri).split("/")[-1]

    def update_tree_ui(self):
        """Extracts concepts from graph data caches and map hierarchies sequentially onto visualization nodes."""
        for item in self.tree.get_children(): self.tree.delete(item)
        filter_txt = self.txt_search.get().lower().strip()
        concepts = set(self.g.subjects(RDF.type, SKOS.Concept))
        
        roots = sorted(list(concepts - set(self.g.subjects(SKOS.broader, None))), key=lambda x: self.get_label(x).lower())
        self.parent_lookup = {self.get_label(s): s for s in concepts}

        def add_node_recursive(parent_id, concept_uri, path_set):
            if concept_uri in path_set: return  
            lbl = self.get_label(concept_uri)
            if filter_txt and filter_txt not in lbl.lower(): return
            node_id = self.tree.insert(parent_id, "end", text=f" └─ {lbl}", values=(str(concept_uri),))
            kids = sorted([(c, self.get_label(c)) for c in self.g.subjects(SKOS.broader, concept_uri)], key=lambda x: x[1].lower())
            for child_uri, _ in kids: add_node_recursive(node_id, child_uri, path_set | {concept_uri})

        for r in roots:
            lbl = self.get_label(r)
            if not filter_txt or filter_txt in lbl.lower():
                root_id = self.tree.insert("", "end", text=f"📂 {lbl}", values=(str(r),))
                kids = sorted([(c, self.get_label(c)) for c in self.g.subjects(SKOS.broader, r)], key=lambda x: x[1].lower())
                for child_uri, _ in kids: add_node_recursive(root_id, child_uri, set())

    def run_create_vocab(self):
        """Initializes an empty compliant SKOS metadata schema file placeholder directly out to structural storage targets."""
        path = filedialog.asksaveasfilename(defaultextension=".ttl", filetypes=[("Turtle Files", "*.ttl")])
        if not path: return
        name = os.path.basename(path).replace(".ttl", "")
        new_g = Graph()
        new_scheme = URIRef(f"http://example.org/{name}")
        new_g.add((new_scheme, RDF.type, SKOS.ConceptScheme))
        new_g.add((new_scheme, SKOS.prefLabel, Literal(name, lang="en")))
        new_g.serialize(destination=path, format="turtle")
        self.clear_all_editor_fields()
        self.load_data(path)

    def run_prepare_new_concept(self):
        """Generates random short unique entity hash IDs to construct unlinked new concept storage spaces."""
        if not self.current_file_path:
            messagebox.showwarning("New Concept", "Please import or create a vocabulary file before generating new concepts!")
            return
            
        self.rebuild_form_grid()
        
        if "uri" in self.entries and self.entries["uri"].winfo_exists():
            self.entries["uri"].configure(state="normal")
            self.entries["uri"].delete(0, "end")
            self.entries["uri"].insert(0, f"http://example.org/concept_{uuid.uuid4().hex[:8]}")
            self.entries["uri"].configure(state="disabled")
            
        for f in ["def", "match_wiki", "match_aat", "match_gnd", "broad"]: 
            if f in self.entries and self.entries[f].winfo_exists(): self.entries[f].delete(0, "end")
            
        for widget in self.lang_entries.values(): 
            if widget.winfo_exists(): widget.delete(0, "end")
            
        for frame in self.alt_label_frames.values():
            if frame.winfo_exists():
                for child in frame.winfo_children(): child.destroy()
                
        self.alt_label_widgets = {lang: [] for lang in self.all_possible_languages}
        self.log("✨ New concept initialization layout ready.")

    def run_delete_concept(self):
        """Performs deep recursive tree deletion actions to drop selected elements and children safely."""
        if "uri" not in self.entries or not self.entries["uri"].winfo_exists(): return
        uri_str = self.entries["uri"].get()
        if not uri_str: return
        uri = URIRef(uri_str)
        children = list(self.g.subjects(SKOS.broader, uri))
        if children and self.delete_target_uri != uri:
            self.log(f"⚠️ DANGER: '{self.get_label(uri)}' holds {len(children)} child nodes! Confirm deletion by clicking DELETE again.")
            self.delete_target_uri = uri
            return
        def remove_node(u):
            for child in list(self.g.subjects(SKOS.broader, u)): remove_node(child)
            self.g.remove((u, None, None)); self.g.remove((None, None, u))
        remove_node(uri)
        self.g.serialize(destination=self.current_file_path, format="turtle")
        self.delete_target_uri = None
        self.rebuild_form_grid()
        self.clear_all_editor_fields()
        self.update_tree_ui()
        self.log("🗑 *Resource wiped from data store.*")

    def run_health_check(self):
        """Scans the active data structures to flag isolated or orphan node elements missing structural metadata links."""
        self.log("🏥 Running rapid semantic health scan...")
        orphans = [self.get_label(s) for s in self.g.subjects(RDF.type, SKOS.Concept) if not list(self.g.objects(s, SKOS.broader)) and not list(self.g.objects(s, SKOS.topConceptOf))]
        if orphans: self.log(f"🚫 Stale orphan nodes detected: {', '.join(orphans)}")
        else: self.log("✅ No orphan nodes. Validation clear.")

    def run_fix_labels(self):
        """Automated string diagnostic repair routine mapping missing concept labels back directly from clean URI strings."""
        self.log("🛠️ Re-indexing and repairing graph strings...")
        c_uri = 0
        for s in self.g.subjects(RDF.type, SKOS.Concept):
            if not list(self.g.objects(s, SKOS.prefLabel)):
                uri_str = str(s)
                raw = uri_str.split("#")[-1] if "#" in uri_str else uri_str.split("/")[-1]
                clean = raw.replace("_", " ").replace("%20", " ").capitalize()
                self.g.add((s, SKOS.prefLabel, Literal(clean, lang="en")))
                c_uri += 1
        self.g.serialize(destination=self.current_file_path, format="turtle")
        self.update_tree_ui()
        self.log(f"✅ Success. Repaired {c_uri} concept resources.")


if __name__ == "__main__":
    root = ctk.CTk()
    root.update()
    app = HECTOREditor(root)
    root.mainloop()