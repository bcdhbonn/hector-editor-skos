import os
import uuid
from rdflib import Graph, Literal, RDF, SKOS, URIRef

class VocabularyManager:
    """
    Manages semantic SKOS graph lifecycles using RDFLib.
    Handles loading, querying, editing, deleting, importing, and exporting.
    """

    def __init__(self):
        self.g = Graph()
        self.current_file_path = ""
        self.scheme_uri = URIRef("http://vocabs.bcdh.uni-bonn.de/scheme")

    def load_data(self, path):
        """Loads a Turtle file into the graph and detects active languages."""
        self.current_file_path = path
        self.g = Graph()
        self.g.parse(self.current_file_path, format="turtle")
        
        schemes = list(self.g.subjects(RDF.type, SKOS.ConceptScheme))
        if schemes:
            self.scheme_uri = schemes[0]
            
        detected_langs = set()
        for _, p, o in self.g:
            if p in [SKOS.prefLabel, SKOS.altLabel] and isinstance(o, Literal) and o.language:
                detected_langs.add(o.language.lower())
        
        if not detected_langs:
            detected_langs = {"de", "en"}
            
        return sorted(list(detected_langs))

    def create_new_vocabulary(self, path, custom_namespace, name):
        """Creates a new vocabulary with a base namespace and concept scheme."""
        self.current_file_path = path
        self.g = Graph()
        if custom_namespace.endswith(("#", "/")):
            self.scheme_uri = URIRef(custom_namespace + "scheme")
        else:
            self.scheme_uri = URIRef(custom_namespace + "#scheme")
        self.g.add((self.scheme_uri, RDF.type, SKOS.ConceptScheme))
        self.g.add((self.scheme_uri, SKOS.prefLabel, Literal(name, lang="en")))
        self.serialize()

    def serialize(self):
        """Serializes the current graph to the loaded file path."""
        if self.current_file_path:
            self.g.serialize(destination=self.current_file_path, format="turtle")

    def get_clean_namespace(self):
        """Deduces a clean absolute HTTP namespace, prioritizing the explicit ConceptScheme URI."""
        if self.scheme_uri:
            sch_str = str(self.scheme_uri)
            if (sch_str.startswith("http://") or sch_str.startswith("https://")) and not sch_str.startswith("file:"):
                if "#" in sch_str:
                    return sch_str.split("#")[0] + "#"
                elif sch_str.endswith(("/scheme", "/Scheme", "/vocabulary", "/Vocabulary")):
                    return "/".join(sch_str.split("/")[:-1]) + "/"
                else:
                    if not sch_str.endswith(("/", "#")):
                        sch_str += "/"
                    return sch_str

        for s in self.g.subjects(RDF.type, SKOS.Concept):
            s_str = str(s)
            if (s_str.startswith("http://") or s_str.startswith("https://")) and not s_str.startswith("file:"):
                if "#" in s_str:
                    return s_str.split("#")[0] + "#"
                else:
                    return "/".join(s_str.split("/")[:-1]) + "/"
        
        if self.current_file_path:
            name = os.path.basename(self.current_file_path).replace(".ttl", "")
            return f"http://vocabs.bcdh.uni-bonn.de/{name}/"
            
        return "http://vocabs.bcdh.uni-bonn.de/vocabulary/"

    def get_label(self, uri, lang=None, active_languages=None, all_possible_languages=None):
        """Gets preferred label of a concept URI, with fallbacks."""
        labels = list(self.g.objects(uri, SKOS.prefLabel))
        if lang:
            for l in labels:
                if getattr(l, "language", None) == lang:
                    return str(l)
        if active_languages:
            for l_code in active_languages:
                for l in labels:
                    if getattr(l, "language", None) == l_code:
                        return str(l)
        if all_possible_languages:
            for l_code in all_possible_languages:
                for l in labels:
                    if getattr(l, "language", None) == l_code:
                        return str(l)
        if labels:
            return str(labels[0])
        return str(uri).split("#")[-1] if "#" in str(uri) else str(uri).split("/")[-1]

    def get_concept_details(self, uri):
        """Retrieves details of a concept: labels, definition, exactMatch mappings, parents."""
        details = {
            "uri": str(uri),
            "pref_labels": [],
            "alt_labels": [],
            "definition": "",
            "broaders": [],
            "match_wiki": "",
            "match_aat": "",
            "match_gnd": ""
        }
        
        for literal in self.g.objects(uri, SKOS.prefLabel):
            lang = getattr(literal, "language", "de")
            details["pref_labels"].append((str(literal), lang))
            
        for literal in self.g.objects(uri, SKOS.altLabel):
            lang = getattr(literal, "language", "de")
            details["alt_labels"].append((str(literal), lang))
            
        details["definition"] = next((str(d) for d in self.g.objects(uri, SKOS.definition)), "")
        
        details["broaders"] = [str(p) for p in self.g.objects(uri, SKOS.broader)]
        
        matches = list(self.g.objects(uri, SKOS.exactMatch))
        for m in matches:
            m_str = str(m)
            if "wikidata.org" in m_str:
                details["match_wiki"] = m_str
            elif "getty.edu" in m_str:
                details["match_aat"] = m_str
            elif "d-nb.info" in m_str:
                details["match_gnd"] = m_str
                
        return details

    def save_concept(self, uri, pref_labels, alt_labels, definition, match_wiki, match_aat, match_gnd, broader_parents):
        """Saves concept fields back to the graph. Replaces existing statements."""
        # Clean existing relations
        for p in [SKOS.prefLabel, SKOS.altLabel, SKOS.definition, SKOS.broader, SKOS.topConceptOf, SKOS.inScheme]:
            self.g.remove((uri, p, None))
        self.g.remove((None, SKOS.hasTopConcept, uri))

        self.g.add((uri, RDF.type, SKOS.Concept))
        self.g.add((uri, SKOS.inScheme, self.scheme_uri))

        for text_val, lang in pref_labels:
            if text_val.strip():
                self.g.add((uri, SKOS.prefLabel, Literal(text_val.strip(), lang=lang)))

        for text_val, lang in alt_labels:
            if text_val.strip():
                self.g.add((uri, SKOS.altLabel, Literal(text_val.strip(), lang=lang)))

        if definition.strip():
            self.g.add((uri, SKOS.definition, Literal(definition.strip())))

        for val in [match_wiki, match_aat, match_gnd]:
            if val.strip():
                self.g.add((uri, SKOS.exactMatch, URIRef(val.strip())))

        has_parents = False
        for p_uri_str in broader_parents:
            if p_uri_str:
                self.g.add((uri, SKOS.broader, URIRef(p_uri_str)))
                has_parents = True

        if not has_parents:
            self.g.add((uri, SKOS.topConceptOf, self.scheme_uri))
            self.g.add((self.scheme_uri, SKOS.hasTopConcept, uri))

        self.serialize()

    def get_child_concepts(self, uri):
        """Returns URIs of child concepts directly under this concept."""
        return list(self.g.subjects(SKOS.broader, uri))

    def delete_concept_recursive(self, uri):
        """Recursively deletes a concept and all of its descendants."""
        to_delete = set()
        stack = [uri]
        while stack:
            curr = stack.pop()
            if curr not in to_delete:
                to_delete.add(curr)
                for child in self.get_child_concepts(curr):
                    if child not in to_delete:
                        stack.append(child)
                        
        for u in to_delete:
            self.g.remove((u, None, None))
            self.g.remove((None, None, u))
        self.serialize()

    def delete_concept_single(self, uri):
        """Deletes a single concept and promotes its children to top concepts of the scheme."""
        children = self.get_child_concepts(uri)
        for child in children:
            self.g.remove((child, SKOS.broader, uri))
            self.g.add((child, SKOS.topConceptOf, self.scheme_uri))
            self.g.add((self.scheme_uri, SKOS.hasTopConcept, child))
        self.g.remove((uri, None, None))
        self.g.remove((None, None, uri))
        self.serialize()

    def get_concepts(self):
        """Returns a set of all concept URIs in the vocabulary."""
        return set(self.g.subjects(RDF.type, SKOS.Concept))

    def get_roots(self):
        """Returns roots of the hierarchy (concepts without parent broader relations)."""
        concepts = self.get_concepts()
        broader_subjects = set(self.g.subjects(SKOS.broader, None))
        return concepts - broader_subjects

    def import_facet(self, facet_graph, parent_uri, align_uris):
        """Imports another graph (facet) under parent_uri, aligning namespaces if requested."""
        current_ns = self.get_clean_namespace()
        facet_schemes = list(facet_graph.subjects(RDF.type, SKOS.ConceptScheme))
        facet_ns = str(facet_schemes[0]).rstrip('#/') + "/" if facet_schemes else "http://example.org/"
        
        facet_concepts = set(facet_graph.subjects(RDF.type, SKOS.Concept))
        facet_has_parent = set(facet_graph.subjects(SKOS.broader, None))
        facet_roots = facet_concepts - facet_has_parent
        
        uri_mapping = {}
        if align_uris:
            for c in facet_concepts:
                uri_mapping[c] = URIRef(f"{current_ns}concept_{uuid.uuid4().hex[:8]}")
        
        def transform_node(uri):
            if uri in uri_mapping:
                return uri_mapping[uri]
            if isinstance(uri, URIRef) and str(uri).startswith(facet_ns) and align_uris:
                return URIRef(str(uri).replace(facet_ns, current_ns))
            return uri

        for s, p, o in facet_graph:
            if s in facet_schemes and p == RDF.type and o == SKOS.ConceptScheme:
                continue
            new_s = transform_node(s)
            new_p = transform_node(p)
            new_o = transform_node(o) if isinstance(o, URIRef) else o
            self.g.add((new_s, new_p, new_o))
            
        for c in facet_concepts:
            new_c = transform_node(c)
            self.g.remove((new_c, SKOS.inScheme, None))
            self.g.add((new_c, SKOS.inScheme, self.scheme_uri))
            
        for r in facet_roots:
            new_r = transform_node(r)
            if parent_uri:
                self.g.add((new_r, SKOS.broader, parent_uri))
                self.g.remove((new_r, SKOS.topConceptOf, None))
            else:
                self.g.add((new_r, SKOS.topConceptOf, self.scheme_uri))
                self.g.add((self.scheme_uri, SKOS.hasTopConcept, new_r))
                
        self.serialize()
        return len(facet_concepts)

    def export_facet(self, root_uri, export_sub_hierarchy, destination_path):
        """Exports a single concept or hierarchy branch to a new Turtle file."""
        export_set = {root_uri}
        if export_sub_hierarchy:
            stack = [root_uri]
            while stack:
                curr = stack.pop()
                for child in self.get_child_concepts(curr):
                    if child not in export_set:
                        export_set.add(child)
                        stack.append(child)
            
        export_g = Graph()
        name = os.path.basename(destination_path).replace(".ttl", "")
        new_scheme = URIRef(self.get_clean_namespace() + name)
        export_g.add((new_scheme, RDF.type, SKOS.ConceptScheme))
        export_g.add((new_scheme, SKOS.prefLabel, Literal(name, lang="en")))
        
        for c in export_set:
            for p, o in self.g.predicate_objects(c):
                if p == SKOS.broader:
                    if o in export_set:
                        export_g.add((c, p, o))
                elif p in [SKOS.topConceptOf, SKOS.hasTopConcept]:
                    continue
                elif p == SKOS.inScheme:
                    export_g.add((c, SKOS.inScheme, new_scheme))
                else:
                    export_g.add((c, p, o))
                    
            if c == root_uri:
                export_g.add((c, SKOS.topConceptOf, new_scheme))
                export_g.add((new_scheme, SKOS.hasTopConcept, c))
            elif export_sub_hierarchy and not list(self.g.objects(c, SKOS.broader)):
                export_g.add((c, SKOS.topConceptOf, new_scheme))
                export_g.add((new_scheme, SKOS.hasTopConcept, c))
                
        export_g.serialize(destination=destination_path, format="turtle")
        return len(export_set)

    def run_health_check(self):
        """Returns names of orphan nodes (concepts missing parent broaders and topConceptOf)."""
        orphans = []
        for s in self.g.subjects(RDF.type, SKOS.Concept):
            if not list(self.g.objects(s, SKOS.broader)) and not list(self.g.objects(s, SKOS.topConceptOf)):
                orphans.append(s)
        return orphans

    def run_fix_labels(self):
        """Fills missing prefLabels based on local name component of URIs."""
        c_uri = 0
        for s in self.g.subjects(RDF.type, SKOS.Concept):
            if not list(self.g.objects(s, SKOS.prefLabel)):
                uri_str = str(s)
                raw = uri_str.split("#")[-1] if "#" in uri_str else uri_str.split("/")[-1]
                clean = raw.replace("_", " ").replace("%20", " ").capitalize()
                self.g.add((s, SKOS.prefLabel, Literal(clean, lang="en")))
                c_uri += 1
        if c_uri > 0:
            self.serialize()
        return c_uri

    def get_concept_turtle(self, uri):
        """Returns the Turtle serialization of a single concept's triples."""
        temp_g = Graph()
        temp_g.bind("skos", SKOS)
        temp_g.bind("rdf", RDF)
        
        ns = self.get_clean_namespace()
        if ns:
            temp_g.bind("", URIRef(ns))
            
        for prefix, namespace in self.g.namespaces():
            if prefix not in ["xml", "rdf", "rdfs", "xsd", ""]:
                temp_g.bind(prefix, namespace)
        
        # Add ONLY triples where the concept is the subject
        for p, o in self.g.predicate_objects(uri):
            temp_g.add((uri, p, o))
            
        val = temp_g.serialize(format="turtle")
        if isinstance(val, bytes):
            return val.decode("utf-8")
        return val
