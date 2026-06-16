# HECTOR-Editor

HECTOR-Editor is a lightweight, responsive desktop application built with Python and CustomTkinter for managing semantic SKOS vocabularies. Tailored for workflows in the Digital Humanities and archaeological data management, it allows researchers to easily build, edit, and serialize structured hierarchical concept schemes.

The editor features integrated APIs to directly link local concepts to major global authority files, ensuring FAIR data principles and high-quality semantic alignments.

## ✨ Key Features
* **SKOS Hierarchy Management:** Visually construct and manage `skos:Concept` hierarchies, broader/narrower relationships, and top concepts.
* **Multilingual Support:** Dynamic UI for managing `skos:prefLabel` and `skos:altLabel` across multiple ISO 639-1 language codes.
* **Polyhierarchical Support:** DConcepts can be linked to multiple broader terms, allowing for a accurate representation of complex knowledge domains and multi-faceted semantic classification.
* **Authority File Integration:** Built-in asynchronous querying and exact matching (`skos:exactMatch`) for:
    * Wikidata API
    * Getty Art & Architecture Thesaurus (AAT)
    * Integrated Authority File (GND)
* **Data Quality Assurance:** Rapid semantic health scans to detect orphan nodes and auto-repair missing URI labels.
* **Turtle Serialization:** Native import and export of robust `.ttl` (Turtle) graphs using RDFLib.

## 🚀 Installation & Usage

1. Clone this repository:
   ```bash
   git clone [https://github.com/bcdhbonn/hector-editor.git](https://github.com/bcdhbonn/hector-editor.git)
   cd hector-editor
