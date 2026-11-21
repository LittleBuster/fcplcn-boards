"""Exact, read-only validation of the approved Upper board rule changes."""
import copy
import json
import re


ISOLATION_RULE = '''(rule "Galvanic domain same-layer clearance"
 (condition "(A.NetName == '/*_ISO' || A.NetName == '/RS485_A' || A.NetName == '/RS485_B' || A.NetName == '/RS485_TERM' || A.NetName == '/RS485_VISO' || A.NetName == '/RS485_VISO_OUT') && !(B.NetName == '/*_ISO' || B.NetName == '/RS485_A' || B.NetName == '/RS485_B' || B.NetName == '/RS485_TERM' || B.NetName == '/RS485_VISO' || B.NetName == '/RS485_VISO_OUT')")
 (constraint clearance (min 1.5mm)))'''


def sexpressions(text):
    """Preserve every rule token while permitting whitespace-only reformatting."""
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', text)
    stack = [[]]
    for token in tokens:
        if token == '(':
            node = []
            stack[-1].append(node)
            stack.append(node)
        elif token == ')':
            assert len(stack) > 1, 'Unbalanced DRC rule parentheses'
            stack.pop()
        else:
            stack[-1].append(token)
    assert len(stack) == 1, 'Unbalanced DRC rule parentheses'
    return stack[0]


def audit_upper_rules(before_project, current_project, before_dru, current_dru):
    before = json.loads(before_project)
    current = json.loads(current_project)
    expected = copy.deepcopy(before)
    rules = expected['board']['design_settings']['rules']
    assert rules['min_via_diameter'] == 0.8, 'Unexpected baseline via diameter'
    assert rules['min_via_annular_width'] == 0.25, 'Unexpected baseline via annulus'
    assert rules['min_through_hole_diameter'] == 0.3, 'Unexpected baseline drill minimum'
    rules['min_via_diameter'] = 0.6
    rules['min_via_annular_width'] = 0.15
    assert current == expected, 'Project differs beyond the two approved via minima'

    expected_dru = sexpressions(before_dru)
    via_rules = [node for node in expected_dru
                 if node[:2] == ['rule', '"Standard via annular ring"']]
    assert len(via_rules) == 1, 'Expected one baseline via-annulus rule'
    via = via_rules[0]
    assert via == ['rule', '"Standard via annular ring"',
                   ['condition', '"A.Type == \'Via\'"'],
                   ['constraint', 'annular_width', ['min', '0.25mm']]], 'Unexpected baseline via-annulus rule'
    via[3][2][1] = '0.15mm'
    expected_dru.extend(sexpressions(ISOLATION_RULE))
    assert sexpressions(current_dru) == expected_dru, 'DRC rules differ beyond the approved via annulus and exact isolation rule'
    return {
        'project_changed_paths': {
            'board.design_settings.rules.min_via_diameter': [0.8, 0.6],
            'board.design_settings.rules.min_via_annular_width': [0.25, 0.15],
        },
        'minimum_through_hole_diameter_mm_unchanged': 0.3,
        'standard_via_annular_rule_mm': [0.25, 0.15],
        'added_exact_galvanic_domain_clearance_mm': 1.5,
        'all_other_project_settings_and_existing_DRC_rules_exact': True,
    }
