import unittest
import os
import shutil
from rdflib import Graph, URIRef, RDF, SKOS, Literal
from hector_core import VocabularyManager

class TestVocabularyManager(unittest.TestCase):
    def setUp(self):
        self.test_dir = "test_run_temp"
        os.makedirs(self.test_dir, exist_ok=True)
        self.vocab_path = os.path.join(self.test_dir, "test_vocab.ttl")
        self.mgr = VocabularyManager()

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_create_and_load(self):
        self.mgr.create_new_vocabulary(
            self.vocab_path,
            "http://example.org/test/",
            "Test Vocab"
        )
        self.assertTrue(os.path.exists(self.vocab_path))
        
        # Load in another manager
        new_mgr = VocabularyManager()
        langs = new_mgr.load_data(self.vocab_path)
        self.assertEqual(new_mgr.scheme_uri, URIRef("http://example.org/test/scheme"))
        self.assertIn("en", langs)

    def test_save_and_retrieve_concept(self):
        self.mgr.create_new_vocabulary(self.vocab_path, "http://example.org/test/", "Test Vocab")
        concept_uri = URIRef("http://example.org/test/concept_1")
        
        pref_labels = [("Concept One", "en"), ("Konzept Eins", "de")]
        alt_labels = [("Synonym One", "en")]
        definition = "This is concept one."
        broader_parents = ["http://example.org/test/parent1"]
        
        # Add parent to vocabulary manager's graph first so it counts as a concept
        self.mgr.g.add((URIRef("http://example.org/test/parent1"), RDF.type, SKOS.Concept))
        
        self.mgr.save_concept(
            concept_uri,
            pref_labels,
            alt_labels,
            definition,
            "http://www.wikidata.org/entity/Q12345",
            "",
            "",
            broader_parents
        )
        
        details = self.mgr.get_concept_details(concept_uri)
        self.assertEqual(details["definition"], "This is concept one.")
        self.assertEqual(len(details["pref_labels"]), 2)
        self.assertEqual(len(details["alt_labels"]), 1)
        self.assertIn("http://example.org/test/parent1", details["broaders"])
        self.assertEqual(details["match_wiki"], "http://www.wikidata.org/entity/Q12345")
        self.assertIn((concept_uri, SKOS.inScheme, self.mgr.scheme_uri), self.mgr.g)

    def test_delete_concept(self):
        self.mgr.create_new_vocabulary(self.vocab_path, "http://example.org/test/", "Test Vocab")
        c1 = URIRef("http://example.org/test/concept_1")
        c2 = URIRef("http://example.org/test/concept_2")
        
        # Create hierarchy: c1 -> c2 (c2 is broader c1? No, c1 broader c2 means c1 is parent of c2, i.e., c2 SKOS.broader c1)
        self.mgr.g.add((c1, RDF.type, SKOS.Concept))
        self.mgr.g.add((c2, RDF.type, SKOS.Concept))
        self.mgr.g.add((c2, SKOS.broader, c1))
        
        # Test delete single concept (promoting child c2 to top concept)
        self.mgr.delete_concept_single(c1)
        self.assertNotIn(c1, self.mgr.get_concepts())
        self.assertIn(c2, self.mgr.get_concepts())
        self.assertIn((c2, SKOS.topConceptOf, self.mgr.scheme_uri), self.mgr.g)

    def test_health_check_and_fix_labels(self):
        self.mgr.create_new_vocabulary(self.vocab_path, "http://example.org/test/", "Test Vocab")
        c1 = URIRef("http://example.org/test/concept_without_label")
        self.mgr.g.add((c1, RDF.type, SKOS.Concept))
        
        # Concept has no broader and no topConceptOf -> Orphan
        orphans = self.mgr.run_health_check()
        self.assertIn(c1, orphans)
        
        # Fix labels
        repaired = self.mgr.run_fix_labels()
        self.assertEqual(repaired, 1)
        self.assertEqual(self.mgr.get_label(c1, lang="en"), "Concept without label")

    def test_cycle_handling(self):
        self.mgr.create_new_vocabulary(self.vocab_path, "http://example.org/test/", "Test Vocab")
        c1 = URIRef("http://example.org/test/concept_1")
        c2 = URIRef("http://example.org/test/concept_2")
        self.mgr.g.add((c1, RDF.type, SKOS.Concept))
        self.mgr.g.add((c2, RDF.type, SKOS.Concept))
        
        # Create a cycle: c1 broader c2, and c2 broader c1
        self.mgr.g.add((c1, SKOS.broader, c2))
        self.mgr.g.add((c2, SKOS.broader, c1))
        
        # Attempting recursive delete on a cycle should complete without RecursionError
        self.mgr.delete_concept_recursive(c1)
        self.assertNotIn(c1, self.mgr.get_concepts())
        self.assertNotIn(c2, self.mgr.get_concepts())

    def test_get_concept_turtle(self):
        self.mgr.create_new_vocabulary(self.vocab_path, "http://example.org/test/", "Test Vocab")
        c1 = URIRef("http://example.org/test/concept_1")
        self.mgr.g.add((c1, RDF.type, SKOS.Concept))
        self.mgr.g.add((c1, SKOS.prefLabel, Literal("Concept 1", lang="en")))
        
        turtle_str = self.mgr.get_concept_turtle(c1)
        self.assertIn("concept_1", turtle_str)
        self.assertIn("Concept 1", turtle_str)
        self.assertIn("a skos:Concept", turtle_str)

if __name__ == "__main__":
    unittest.main()
