from desktop_decision_v2 import decision_v2_lines

def test_empty(): assert 'sin datos' in decision_v2_lines({})[0]
def test_safety_visible(): assert decision_v2_lines({'decision_v2':{'ok':True}})[-1]=='Trading real · OFF'
def test_champion_visible(): assert decision_v2_lines({'decision_v2':{'ok':True,'champion':{'action':'HOLD'}}})[0]=='CHAMPION · HOLD'
def test_error_visible(): assert 'ERROR' in decision_v2_lines({'decision_v2':{'ok':False,'error':'boom'}})[0]
