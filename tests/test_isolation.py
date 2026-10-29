import copy,unittest
from wctr.isolation import compile_source,Adapter,alias_fork,graph

def model(code):return compile_source(code,'fixture.py')['Model']()

CODE='''
class Model:
    def predict_belief(self,s,a):
        n=s.copy()
        if a=='move':n['objects'][0]['x'] += 1
        elif a=='new':n['objects'][1]['x'] = 5
        elif a=='fail':
            n['objects'][0]['x']=77
            raise RuntimeError('expected')
        return n
'''

class Tests(unittest.TestCase):
    def test_inplace_augmented_list_preserves_parent(self):
        code='''
class Model:
    def predict_belief(self,s,a):
        n=s.copy()
        n['x'] += [3]
        return n
'''
        a=Adapter(model(code),'journal');s={'x':[1,2]}
        self.assertEqual(a.transition(s,'go'),{'x':[1,2,3]})
        self.assertEqual(s,{'x':[1,2]})
    def test_journal_grafts_result_and_restores_parent(self):
        m=model(CODE);a=Adapter(m,'journal');s={'objects':[{'x':0},{'x':2}]}
        n=a.transition(s,'move')
        self.assertEqual(s['objects'][0]['x'],0);self.assertEqual(n['objects'][0]['x'],1)
        n2=a.transition(n,'move')
        self.assertEqual(n['objects'][0]['x'],1);self.assertEqual(n2['objects'][0]['x'],2)
    def test_unseen_mutation_deoptimizes(self):
        a=Adapter(model(CODE));s={'objects':[{'x':0},{'x':2}]}
        a.calibrate([(s,'move')]);a.transition(s,'new')
        self.assertEqual(s['objects'][1]['x'],2);self.assertEqual(a.deopts,1)
    def test_alias_closure_and_cycle(self):
        item={'x':0};s={'objects':[item],'selected':item};s['cycle']=s
        n,count=alias_fork(s,{id(item)})
        self.assertIs(n['objects'][0],n['selected']);self.assertIs(n['cycle'],n)
        self.assertIsNot(n['selected'],s['selected'])
    def test_exception_restores(self):
        a=Adapter(model(CODE));s={'objects':[{'x':0},{'x':2}]}
        with self.assertRaises(RuntimeError):a.transition(s,'fail')
        self.assertEqual(s['objects'][0]['x'],0)
    def test_assignment_evaluation_order(self):
        code='''
class Model:
    def predict_belief(self,s,a):
        n=s.copy()
        n['x'][0]=n['x'].pop()
        return n
'''
        m=model(code);a=Adapter(m,'journal');s={'x':[1,2,3]}
        self.assertEqual(a.transition(s,'go'),{'x':[3,2]});self.assertEqual(s,{'x':[1,2,3]})
    def test_selector_copies_only_matching_object(self):
        code='''
class Model:
    def predict_belief(self,s,a):
        n=s.copy()
        for obj in n['objects']:
            if a.endswith(obj['name']):obj['x']=0
        return n
'''
        a=Adapter(model(code));s={'objects':[{'name':'A','x':4},{'name':'B','x':8}]}
        a.calibrate([(s,'go A')]);n=a.transition(s,'go B')
        self.assertEqual(a.deopts,0);self.assertEqual(s['objects'][1]['x'],8)
        self.assertEqual(n['objects'][1]['x'],0)
        self.assertIs(n['objects'][0],s['objects'][0])

if __name__=='__main__':unittest.main(verbosity=2)
