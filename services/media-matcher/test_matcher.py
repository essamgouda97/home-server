import unittest
from matcher import build_payload, normalize, title_evidence, validate_output


class MatcherTests(unittest.TestCase):
    def test_arabic_diacritics(self):
        self.assertEqual(normalize('أَحلام ـ القاهرة'),normalize('احلام القاهرة'))

    def test_whole_title_and_year(self):
        movie={'title':'The Stories','originalTitle':'القصص','year':2026}
        self.assertEqual(title_evidence(movie,{'title':'القصص 2025 1080p'}),(True,True))
        self.assertEqual(title_evidence(movie,{'title':'The Stories 1999'}),(True,False))
        self.assertFalse(title_evidence(movie,{'title':'My Stories 2026'})[0])

    def test_no_credentials_or_urls_in_payload(self):
        payload=build_payload({'title':'Test','year':2026,'apiKey':'secret'},[{'title':'Test https://x.invalid/?passkey=SECRET','downloadUrl':'PRIVATE','password':'PASSWORD'}])
        self.assertNotIn('SECRET',str(payload))
        self.assertNotIn('PRIVATE',str(payload))
        self.assertNotIn('PASSWORD',str(payload))

    def test_output_must_classify_only_real_ids(self):
        for data in [
            {'matches':[{'id':99,'verdict':'same'}]},
            {'matches':[{'id':True,'verdict':'same'}]},
            {'matches':[]},
            {'matches':[{'id':0,'verdict':'same','command':'download'}]},
            {'matches':[{'id':0,'verdict':'same'},{'id':0,'verdict':'same'}]},
        ]:
            with self.assertRaises(ValueError):validate_output(data,1)

    def test_valid_output(self):
        result={'matches':[{'id':0,'verdict':'uncertain'}]}
        self.assertEqual(validate_output(result,1),result['matches'])


if __name__=='__main__':unittest.main()
