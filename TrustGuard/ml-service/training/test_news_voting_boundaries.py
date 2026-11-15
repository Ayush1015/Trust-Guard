"""Both news paths: search coverage is display-only, not a truth vote.
All external calls are mocked. This tests code paths, not current sources.
"""
import os,sys,json,unittest
from unittest.mock import patch
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main
import services.entailment_service as nli
class VotingBoundaryTests(unittest.TestCase):
 def test_both_paths_never_vote_coverage(self):
  patches={
   'local_news_prediction':lambda _:main.make_prediction('Direct model','Fake',90),
   'pretrained_text_predictions':lambda *a:[], 'hf_news_predictions':lambda *a:[],
   'heuristic_news_vote':lambda *a:None,
   'check_article_url_trust':lambda *a:{'checked':[],'anyUntrustworthy':False},
   'pib_fact_check':lambda *a:{'available':False,'covered':False,'label':'Unknown','explanation':'not checked','sources':[]},
   'search_based_url_trust':lambda *a:{'coverageFound':True,'totalChecked':10,'trustedCount':10},
   'gemini_news_check':lambda *a:{'available':False,'label':'Unknown','mode':'offline','explanation':'not checked','sources':[]},
   'search_related_articles':lambda *a:[], 'duckduckgo_related':lambda *a,**kw:[],
   'collect_related_articles':lambda *a,**kw:None,
   'pretrained_models':[], 'hf_news_classifiers':[], 'ENABLE_WEB_SEARCH_VERIFICATION':False,
  }
  with patch.multiple(main,**patches),patch.object(nli,'is_available',return_value=False):
   normal=main.analyze_news(main.NewsPayload(text='The central bank raised interest rates on Tuesday.'),None)
   frames=list(main.stream_news_analysis('The central bank raised interest rates on Tuesday.','','',None))
   final=[json.loads(f.split('data: ',1)[1]) for f in frames if f.startswith('event: final_result')]
  self.assertEqual(len(final),1,frames)
  for r in [normal,final[0]]:
   self.assertEqual(r['poll']['totalVotes'],1,r)
   self.assertEqual(r['poll']['winner'],'Fake')
   self.assertFalse(any(p['model']=='Search Coverage Trust' for p in r['models']))
 def test_source_weight_cap(self):
  verification={'sources':[{'verdict':'supports','entailment':.99,'title':str(i)} for i in range(12)]}
  preds=nli.verification_to_predictions(verification,main.make_prediction)
  self.assertLessEqual(sum(p['weight'] for p in preds),1.000001)
 def test_source_only_abstains(self):
  pred=main.make_prediction('Estimated source','Real',99,source='nli_evidence',weight=.25)
  pred['evidenceType']='estimated_entailment'
  p=main.model_poll([pred],'Fake News')
  self.assertTrue(p['abstain']);self.assertIn('no_direct_claim_model',p['abstainReasons'])
 def test_copied_bodies_and_www_do_not_stack(self):
  text='The central bank raised interest rates by half a percentage point on Tuesday. '*5
  articles=[{'url':'https://example.com/a','title':'First title','text':text},{'url':'https://www.example.com/b','title':'Second title','text':text+' Different last sentence.'},{'url':'https://copy.example.net/c','title':'Third title','text':text}]
  with patch.object(nli,'is_available',return_value=True),patch.object(nli,'check_source',return_value={'available':True,'verdict':'supports'}):
   r=nli.verify_claim_against_articles('The bank raised rates',articles)
  self.assertEqual(len(r['sources']),1)
 def test_style_check_abstains_without_risk_markers(self):
  import trust_extras
  maker=lambda name,label,conf,**kw:{'model':name,'label':label,'confidence':conf,**kw}
  calm='The council published the minutes of its meeting on Tuesday. The document lists the agenda items discussed.'
  self.assertIsNone(trust_extras.heuristic_news_vote('Council publishes minutes',calm,maker))
  risky="SHOCKING TRUTH: doctors hate this one trick!!! You won't believe the miracle cure they don't want!!!"
  vote=trust_extras.heuristic_news_vote(risky,'',maker)
  self.assertIsNotNone(vote);self.assertEqual(vote['label'],'Fake')
 def test_model_status_reflects_actual_active_models(self):
  status=main.model_status()
  flat=[m for models in status['active'].values() for m in models]
  self.assertNotIn('Heuristic Spam Pattern',flat)
  self.assertFalse(any('SSL' in m for m in flat),flat)
  self.assertFalse(any(('redirect' in m.lower()) and ('no redirect' not in m.lower()) for m in flat),flat)
  for entry in main.hf_news_classifiers:
   self.assertIn(entry['name'],status['active']['news'])
  self.assertEqual(status['totalActive'],sum(len(v) for v in status['active'].values()))
 def test_actual_two_two_tie_abstains_on_both_paths(self):
  # The real Artemis case: Local Fake + Roberta Fake vs two HF Real,
  # no retrieved sources. This displayed MOSTLY TRUE before the fix.
  preds=[
   main.make_prediction('HF: AI-Fake_News_Detection_Roberta','Fake',99.78),
   main.make_prediction('HF: fake-news-detector','Real',98.80),
   main.make_prediction('HF: fake-news-bert','Real',91.62),
   main.make_prediction('Local News Model','Fake',62.55),
  ]
  p=main.model_poll(preds,'Fake News')
  self.assertTrue(p['abstain'],p)
  self.assertIn('tied_votes',p['abstainReasons'])
  self.assertEqual(p['verdictStatus'],'uncertain')
  patches={
   'local_news_prediction':lambda _:main.make_prediction('Local News Model','Fake',62.55),
   'pretrained_text_predictions':lambda *a:[],
   'hf_news_classifiers':[{'name':'HF: fake-news-detector','repo_id':'a'},{'name':'HF: fake-news-bert','repo_id':'b'},{'name':'HF: AI-Fake_News_Detection_Roberta','repo_id':'c'}],
   'hf_news_prediction':lambda entry,_c: main.make_prediction(entry['name'],'Fake' if 'Roberta' in entry['name'] else 'Real',{'HF: fake-news-detector':98.80,'HF: fake-news-bert':91.62,'HF: AI-Fake_News_Detection_Roberta':99.78}[entry['name']]),
   'heuristic_news_vote':lambda *a:None,
   'check_article_url_trust':lambda *a:{'checked':[],'anyUntrustworthy':False},
   'pib_fact_check':lambda *a:{'available':False,'covered':False,'label':'Unknown','explanation':'not checked','sources':[]},
   'search_based_url_trust':lambda *a:{'coverageFound':False,'totalChecked':0,'trustedCount':0},
   'gemini_news_check':lambda *a:{'available':True,'label':'Unknown','mode':'offline','explanation':'offline fallback, nothing found','sources':[]},
   'search_related_articles':lambda *a:[], 'duckduckgo_related':lambda *a,**kw:[],
   'collect_related_articles':lambda *a,**kw:None,
   'pretrained_models':[], 'ENABLE_WEB_SEARCH_VERIFICATION':False,
  }
  with patch.multiple(main,**patches),patch.object(nli,'is_available',return_value=False):
   normal=main.analyze_news(main.NewsPayload(text='Tie-case check: the space agency confirmed its crewed lunar flyby mission timeline for next year.'),None)
   frames=list(main.stream_news_analysis('Tie-case check: the space agency confirmed its crewed lunar flyby mission timeline for next year.','','',None))
   final=[json.loads(f.split('data: ',1)[1]) for f in frames if f.startswith('event: final_result')]
  for r in [normal,final[0]]:
   self.assertTrue(r['poll']['abstain'],r['poll'])
   self.assertIn('tied_votes',r['poll']['abstainReasons'])
   syn=r.get('pythonSynthesis') or {}
   self.assertEqual(syn.get('classification'),'INSUFFICIENT EVIDENCE',syn)
   self.assertEqual(syn.get('basis'),'python_only',syn)  # offline fallback must not claim web verification
 def test_unequal_confidence_tie_abstains_on_both_paths(self):
  # 1-1 vote tie, Real 99% vs Fake 51%: confidences are uncalibrated and
  # cross-model, so they cannot break a vote tie. Must stay Uncertain.
  preds=[
   main.make_prediction('Local News Model','Real',99.0),
   main.make_prediction('HF: fake-news-detector','Fake',51.0),
  ]
  p=main.model_poll(preds,'Fake News')
  self.assertTrue(p['abstain'],p)
  self.assertIn('tied_votes',p['abstainReasons'])
  self.assertEqual(p['verdictStatus'],'uncertain')
  self.assertTrue(p['isTie'],p)
  patches={
   'local_news_prediction':lambda _:main.make_prediction('Local News Model','Real',99.0),
   'pretrained_text_predictions':lambda *a:[],
   'hf_news_classifiers':[{'name':'HF: fake-news-detector','repo_id':'a'}],
   'hf_news_prediction':lambda entry,_c: main.make_prediction(entry['name'],'Fake',51.0),
   'heuristic_news_vote':lambda *a:None,
   'check_article_url_trust':lambda *a:{'checked':[],'anyUntrustworthy':False},
   'pib_fact_check':lambda *a:{'available':False,'covered':False,'label':'Unknown','explanation':'not checked','sources':[]},
   'search_based_url_trust':lambda *a:{'coverageFound':False,'totalChecked':0,'trustedCount':0},
   'gemini_news_check':lambda *a:{'available':True,'label':'Unknown','mode':'offline','explanation':'offline fallback, nothing found','sources':[]},
   'search_related_articles':lambda *a:[], 'duckduckgo_related':lambda *a,**kw:[],
   'collect_related_articles':lambda *a,**kw:None,
   'pretrained_models':[], 'ENABLE_WEB_SEARCH_VERIFICATION':False,
  }
  with patch.multiple(main,**patches),patch.object(nli,'is_available',return_value=False):
   normal=main.analyze_news(main.NewsPayload(text='Unequal-confidence tie check: a city council approved its annual transit budget on Tuesday.'),None)
   frames=list(main.stream_news_analysis('Unequal-confidence tie check: a city council approved its annual transit budget on Tuesday.','','',None))
   final=[json.loads(f.split('data: ',1)[1]) for f in frames if f.startswith('event: final_result')]
  for r in [normal,final[0]]:
   self.assertTrue(r['poll']['abstain'],r['poll'])
   self.assertIn('tied_votes',r['poll']['abstainReasons'])
   syn=r.get('pythonSynthesis') or {}
   self.assertEqual(syn.get('classification'),'INSUFFICIENT EVIDENCE',syn)
   self.assertEqual(syn.get('basis'),'python_only',syn)
 def test_bare_year_counts_as_dated_reference(self):
  from services.claim_service import build_structured_claim
  claim=build_structured_claim('NASA confirms the Artemis II crewed mission around the Moon is scheduled for 2026.','')
  self.assertTrue(claim.has_explicit_time_reference,claim.to_dict())
if __name__=='__main__':unittest.main()
