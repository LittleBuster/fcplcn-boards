"""Read-only source guard for the two additional isolated DATA ports.

Native DRC/ERC and independent physical copper connectivity remain separate
checks. This audit binds the exact delivered change, preserving protected nets.
"""
from pathlib import Path
from board_paths import board_file, board_dir
import argparse, collections, copy, hashlib, json
import xml.etree.ElementTree as ET
import audit_power_emi_revision as base
import pcbnew as p

NEW = {'U15','D10','R57','R58','R59','R60','C48','C49','C50','C51'}
MOVABLE = {'C14','C15','C22','R56','C39'}
ALLOWED_COPPER = {'/+12V_LOGIC','/+3V3','/+3V3_RS485','/+5V_ISO','/GND','/GND_ISO',
                  '/DATA1_ISO','/DATA2_ISO','/DATA3_ISO','/DATA4_ISO','/DATA6_ISO','/DATA2_CPU','/DATA7_CPU','/DATA8_CPU','/DATA7_ISO','/DATA8_ISO',
                  '/RS485_RX_RAW'}
PROTECTED = {'/USB_DP','/USB_DN','/USB_DP_CPU','/USB_DN_CPU','/USB_CC1','/USB_CC2',
             '/USB_VBUS','/USB_VBUS_SENSE','/ESP_BOOT','/ESP_EN'}

def canonical(tree):
    """Ignore native sibling serialization order and net integer identifiers."""
    if not isinstance(tree,list): return tree
    if tree and tree[0]=='net': return ['net',tree[-1]]
    return [canonical(x) for x in tree]

def xmlmap(root):
    return {(n.get('ref'),n.get('pin')):net.get('name')
            for net in root.findall('nets/net') for n in net.findall('node')}

def run(root,before):
    paths=[root/'Stack-mechanics.json',before/'Stack-mechanics.json']
    for b in ('Upper','Lower'):
        for ext in ('.kicad_pcb','.kicad_sch','.kicad_pro','.kicad_dru','.xml'):
            paths += [board_file(q,b,ext) for q in (root,before)]
    hashes={str(f):base.sha(f) for f in paths}
    assert base.sha(paths[0])==base.sha(paths[1]),'Stack mechanics changed'
    for ext in ('.kicad_pcb','.kicad_sch','.kicad_pro','.kicad_dru','.xml'):
        f='FCPLCN-RLY-1616-1v0'+ext
        assert base.sha(board_dir(root,'Lower')/f)==base.sha(board_dir(before,'Lower')/f),'Lower changed: '+ext
    for ext in ('.kicad_pro','.kicad_dru'):
        f='FCPLCN-CPU-08-1v0'+ext
        assert base.sha(board_dir(root,'Upper')/f)==base.sha(board_dir(before,'Upper')/f),'Upper project/rules changed'
    boards=[p.LoadBoard(str(q/'FCPLCN-CPU-08-1v0/FCPLCN-CPU-08-1v0.kicad_pcb')) for q in (before,root)]
    old,new=boards;fps=[{f.GetReference():f for f in b.GetFootprints()} for b in boards]
    assert set(fps[1])-set(fps[0])==NEW and not(set(fps[0])-set(fps[1])),'Component inventory delta'
    ast=[base.parse((q/'FCPLCN-CPU-08-1v0/FCPLCN-CPU-08-1v0.kicad_pcb').read_text()) for q in (before,root)]
    afps=[base.fps_ast(a) for a in ast]
    assert base.children(ast[0],{'gr_rect','gr_line','gr_arc','gr_poly','gr_circle'})==base.children(ast[1],{'gr_rect','gr_line','gr_arc','gr_poly','gr_circle'}),'Board graphics changed; review labels/outline delta explicitly'
    moved={};changed=[]
    for ref,fp in fps[0].items():
        oldn,newn=base.netmap(fp),base.netmap(fps[1][ref])
        if ref=='U1':
            expected=dict(oldn);expected.update({'31':'/DATA7_CPU','36':'/DATA8_CPU'})
            assert newn==expected,'Unexpected U1 pin assignment'
            assert base.pose(fp)==base.pose(fps[1][ref]),'U1 moved'
            assert base.local_pad_geometry(fp)==base.local_pad_geometry(fps[1][ref]),'U1 pad geometry changed'
            continue
        if ref=='J3':
            assert base.pose(fp)[:4]==base.pose(fps[1][ref])[:4],'J3 origin/rotation changed'
            assert newn=={**{str(i):f'/DATA{i}_ISO' for i in range(1,9)},'9':'/+5V_ISO','10':'/GND_ISO'}
            assert fps[1][ref].GetFPIDAsString()=='RelayStack:KF128-2.54-10P'
            continue
        assert newn==oldn,ref+' net map changed'
        left,right=canonical(afps[0][ref]),canonical(afps[1][ref])
        if ref in MOVABLE:
            if base.pose(fp)!=base.pose(fps[1][ref]):moved[ref]={'before':base.pose(fp),'after':base.pose(fps[1][ref])}
            left,right=base.footprint_without_pose(left),base.footprint_without_pose(right)
        assert base.footprint_equal(left,right),ref+' unexpected footprint/content/pose change'
    oldpads={v[0]:v for v in base.local_pad_geometry(fps[0]['J3'])};newpads={v[0]:v for v in base.local_pad_geometry(fps[1]['J3'])}
    assert all(oldpads[n]==newpads[n] for n in map(str,range(1,9))),'J3 old pin geometry changed'
    copper=[base.copper(b) for b in boards]
    delta=base.copper_delta(*copper,ALLOWED_COPPER)
    assert all(base.geometry_counter(copper[0],n)==base.geometry_counter(copper[1],n) for n in PROTECTED),'Protected copper changed'
    xm=[ET.parse(q/'FCPLCN-CPU-08-1v0/FCPLCN-CPU-08-1v0.xml').getroot() for q in (before,root)]
    maps=list(map(xmlmap,xm));expected=dict(maps[0]);expected.update({('U1','31'):'/DATA7_CPU',('U1','36'):'/DATA8_CPU',('J3','7'):'/DATA7_ISO',('J3','8'):'/DATA8_ISO'})
    for key,value in expected.items():assert maps[1][key]==value,('Existing schematic pin changed',key)
    newnodes={key:value for key,value in maps[1].items() if key not in maps[0]}
    assert set(ref for ref,pin in newnodes)==NEW|{'J3'} and len(newnodes)==29,'Unexpected new node set'
    assert hashes=={str(f):base.sha(f) for f in paths},'Files changed during read-only audit'
    return {'status':'PASS','source_sha256':hashes,'Lower_native_sources_byte_exact':True,'stack_mechanics_byte_exact':True,'Upper_project_rules_byte_exact':True,'new_refs':sorted(NEW),'approved_existing_pose_changes':moved,'U1_only_GPIO38_GPIO44_assigned':True,'existing_schematic_connections_preserved_except_J3_power_repin':True,'J3_existing_eight_pad_geometries_exact':True,'protected_USB_BOOT_EN_copper_exact':True,'copper_delta':delta,'zone_definitions_before':base.zone_definitions(ast[0]),'zone_definitions_after':base.zone_definitions(ast[1]),'limits':'Source audit only; zone changes and new copper require native DRC and separate physical connectivity proof.','CAD_files_not_written':True}

def main():
    import wx
    app=wx.App(False);wx.Log.EnableLogging(False)
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--project-root',type=Path,required=True);a.add_argument('--before-root',type=Path,required=True);a.add_argument('--output',type=Path,required=True);args=a.parse_args()
    d=run(args.project_root,args.before_root);args.output.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':d['status'],'copper_delta':d['copper_delta']['counts'],'moved':d['approved_existing_pose_changes']},ensure_ascii=False))
if __name__=='__main__':main()
