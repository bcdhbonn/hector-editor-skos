# LVR Grabungsrichtlinien SKOS Vocabulary

This directory contains the compiled SKOS vocabulary: **`LVR_Grabungsrichtlinien.ttl`**.

It represents a unified, hierarchical version of the official excavation guidelines (*Grabungsrichtlinien*) of the **Landschaftsverband Rheinland (LVR)**.

---

## 🌐 Namespace & URI Scheme

* **Base Namespace:** `http://vocabs.bcdh.uni-bonn.de/lvr/`
* **Namespace Prefix:** `lvr`
* **Abstract URIs:** To ensure URI stability and prevent label collisions (since some identical terms exist in different facets), all concepts use abstract URIs of the format:
  `http://vocabs.bcdh.uni-bonn.de/lvr/c_<hash>`
  * The `c_<hash>` represents a stable, 8-character SHA-256 hash computed from the category key and the term's German name.

---

## 📂 Vocabulary Facets

The vocabulary integrates five main semantic facets:

1. **Befundansprachen (Feature Classifications):** Systematics of archaeological features (e.g., pits, ovens, posts, tombs).
2. **Datierungen (Dating & Chronology):** Chronological terms and geological/archaeological eras.
   * **Hierarchy Builder:** This facet uses an automatic *interval-containment nesting algorithm*. For each dating term, the parser maps its `Von` (start year) and `Bis` (end year) range. It nests narrower intervals (e.g., *Kambrium*) within their enclosing broader intervals (e.g., *Paläozoikum*), generating a mathematically correct hierarchical timeline.
3. **Fundansprachen (Find & Artifact Classifications):** Classifications of artifacts, tools, ornaments, and mobile finds.
4. **Material (Materials):** Classifications of geological, mineral, and organic materials (e.g., minerals, woods, metals).
5. **Merkmal (Attributes & Characteristics):** Descriptive attributes and traits (e.g., fortified, cultic, round).

---

## 📜 Provenance & Metadata

Every concept is enriched with standard provenance attributes:
* **Creator:** `Landschaftsverband Rheinland (LVR)` (`dcterms:creator`)
* **Source:** LVR excavation guidelines homepage link (`dcterms:source`)
* **Scope Notes:** Explanations and usage hints from the guidelines are stored as `skos:scopeNote`.
* **Dating Attributes:** Original start and end years are stored using the custom properties `lvr:von` and `lvr:bis`.
