"""Paired RLL MCR zones with an unconditional end and bounded control flow."""
from .integer_math import CONTROLLERS
from .model import ModelError,operations

CONDITIONS=frozenset(('XIC','XIO','AFI','EQU','NEQ','LES','LEQ','GRT','GEQ','LIM','MEQ','CMP'))


def profile(project):
    if project.version!='35' or project.processor.upper() not in CONTROLLERS:
        raise ModelError('MCR requires the v35 ControlLogix 5580 software profile')


def plan(project,routine,labels):
    if not any(op.name=='MCR' for rung in routine.rungs for op in operations(rung['nodes'])):return {}
    profile(project)
    if routine.kind!='RLL':raise ModelError('MCR is available only in ladder')
    result={};zones={};opening=None
    for index,rung in enumerate(routine.rungs):
        nodes=rung['nodes'];found=[op for op in operations(nodes) if op.name=='MCR']
        if not found:continue
        if len(found)!=1 or not nodes or nodes[-1] is not found[0] or found[0].args:
            raise ModelError('MCR must be the last unbranched instruction, with no operands')
        if opening is None:
            if any(op.name not in CONDITIONS for op in operations(nodes[:-1])):
                raise ModelError('MCR opening rung requires only condition instructions before MCR')
            opening=index;result[index]='open'
        else:
            if len(nodes)!=1:raise ModelError('MCR end must be unconditional; nested/conditional endings remain unqualified')
            result[index]='close'
            for body in range(opening+1,index):result[body]='body';zones[body]=opening
            opening=None
    if opening is not None:raise ModelError('MCR requires a paired unconditional end in the same routine')
    for index,rung in enumerate(routine.rungs):
        for op in operations(rung['nodes']):
            if index in zones and op.name in ('SBR','RET','TND'):
                raise ModelError('SBR/RET/TND inside an MCR zone remain unqualified')
            if op.name=='JMP' and len(op.args)==1:
                target=labels.get(op.args[0].casefold())
                if target is not None and zones.get(index)!=zones.get(target):
                    raise ModelError('JMP cannot cross an MCR zone boundary')
    return result


def description():
    return dict(profile='v35-5580-paired-MCR',language='RLL',
                opening='Condition instructions followed by a final unbranched MCR()',ending='Paired unconditional MCR() in the same routine',
                disabled='Every body instruction receives false rung input; normal false execution is retained',
                scope='Per routine invocation, including supported RLL AOIs; no stored override between calls',
                prescan='MCR has no action; normal routine prescan still visits the body',native_runtime_parity=False,
                remaining=['Unterminated/conditional/nested zones','Cross-boundary jumps and SBR/RET/TND inside zones',
                           'Opening-rung side effects','Other controller profiles and native scan/fault/CPU parity'])
