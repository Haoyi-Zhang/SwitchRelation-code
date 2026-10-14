import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import direct_checks


class DirectPathTests(unittest.TestCase):
    def case(self):
        return {'id':'own_direct','family':'own_direct','variables':[],
                'buffers':{'a':[1,0]},
                'reference':[{'op':'strlen','buf':'a','off':0,'out':'n'},
                             {'op':'emit','value':'$n'}],
                'candidate':[{'op':'const','value':0,'out':'n'},
                             {'op':'emit','value':'$n'}],
                'expected':'different'}

    def test_real_three_paths_preserve_intended_difference(self):
        self.assertEqual(direct_checks.checked_pair(self.case(),()),
                         [['accept',[1]],['accept',[0]]])

    def rejected_backend(self, corrupt_strings):
        original=direct_checks.producer.Machine
        def machine(case,values,strings):
            result=original(case,values,strings=strings)
            if strings==corrupt_strings:
                result.run=lambda program:['accept',[-1]]
            return result
        with patch.object(direct_checks.producer,'Machine',side_effect=machine):
            with self.assertRaisesRegex(ValueError,'concrete implementation mismatch'):
                direct_checks.checked_pair(self.case(),())

    def test_list_backend_disagreement_is_rejected(self):
        self.rejected_backend(False)

    def test_string_backend_disagreement_is_rejected(self):
        self.rejected_backend(True)


if __name__=='__main__':
    unittest.main()
