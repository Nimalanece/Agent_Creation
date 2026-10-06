import asyncio
import json
import re
import traceback
import urllib.request
from html import unescape
from typing import List, Dict, Any

from app.services.orchestrator_service import run_full_pipeline


def _extract_attrs(tag_html: str) -> Dict[str, str]:
    attrs = {}
    for match in re.finditer(r"(\w+)\s*=\s*\"([^\"]*)\"", tag_html):
        attrs[match.group(1)] = unescape(match.group(2))
    for match in re.finditer(r"(\w+)\s*=\s*'([^']*)'", tag_html):
        attrs[match.group(1)] = unescape(match.group(2))
    return attrs


class ScenarioGenerator:
    def __init__(self, analysis: Dict[str, Any], url: str):
        self.analysis = analysis or {}
        self.url = url
        self.elements = self._discover_elements()

    def _discover_elements(self) -> List[Dict[str, Any]]:
        # Try to use existing analysis output
        candidates = []
        if isinstance(self.analysis.get('elements'), list):
            candidates = self.analysis.get('elements')
        elif isinstance(self.analysis.get('page'), dict) and isinstance(self.analysis['page'].get('elements'), list):
            candidates = self.analysis['page']['elements']

        if candidates:
            # Normalize element objects to expected shape
            normalized = []
            for e in candidates:
                normalized.append({
                    'element_name': e.get('label') or e.get('element_name') or e.get('name') or e.get('id'),
                    'element_type': e.get('element_type') or e.get('type') or 'input',
                    'id': e.get('id'),
                    'name': e.get('name'),
                    'data-testid': e.get('data-testid') if 'data-testid' in e else e.get('data_testid'),
                    'label': e.get('label') or e.get('element_name'),
                    'required': e.get('required', False),
                    'validation_rules': e.get('validation_rules', {}),
                })
            return normalized

        # Fallback: fetch the page and discover inputs, textareas, buttons
        try:
            with urllib.request.urlopen(self.url, timeout=10) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
        except Exception:
            html = ''

        elements = []
        for match in re.finditer(r"<(input|textarea|button)([^>]*)>(?:.*?)</?\1>?", html, flags=re.IGNORECASE | re.DOTALL):
            tag, body = match.group(1).lower(), match.group(2)
            attrs = _extract_attrs(body)
            element = {
                'element_name': attrs.get('id') or attrs.get('name') or attrs.get('data-testid') or f"{tag}_unknown",
                'element_type': 'textarea' if tag == 'textarea' else ('button' if tag == 'button' else attrs.get('type', 'input')),
                'id': attrs.get('id'),
                'name': attrs.get('name'),
                'data-testid': attrs.get('data-testid') or attrs.get('data_testid'),
                'label': attrs.get('aria-label') or attrs.get('placeholder') or attrs.get('id') or attrs.get('name'),
                'required': 'required' in body.lower() or attrs.get('required') in ('true', 'required'),
                'validation_rules': {},
            }
            elements.append(element)

        # Also try to detect a results container with id 'output'
        if re.search(r'id\s*=\s*"output"', html, flags=re.IGNORECASE):
            elements.append({
                'element_name': 'Submission Output',
                'element_type': 'container',
                'id': 'output',
                'name': None,
                'data-testid': None,
                'label': 'Submission Output Area',
                'required': False,
                'validation_rules': {},
            })

        return elements

    def _find_field(self, keywords: List[str]) -> List[Dict[str, Any]]:
        found = []
        for e in self.elements:
            key = (e.get('id') or '') + ' ' + (e.get('name') or '') + ' ' + (e.get('label') or '')
            if any(k.lower() in key.lower() for k in keywords):
                found.append(e)
        return found

    def generate(self) -> Dict[str, Any]:
        # Infer fields
        name_field = (self._find_field(['name', 'full']) + [None])[0]
        email_field = (self._find_field(['email', 'mail']) + [None])[0]
        current_address = (self._find_field(['current address', 'currentAddress', 'current']) + [None])[0]
        permanent_address = (self._find_field(['permanent address', 'permanentAddress', 'permanent']) + [None])[0]
        submit_btn = (self._find_field(['submit', 'button', 'send']) + [None])[0]
        output_container = (self._find_field(['output', 'result', 'submission']) + [None])[0]

        # Build business-readable steps (no locators, no automation terms)
        business_steps = []
        step_no = 1
        business_steps.append({"step_number": step_no, "description": "Open the page where the contact information is entered."})
        step_no += 1
        if name_field:
            business_steps.append({"step_number": step_no, "description": "Enter a realistic full name for the user."})
            step_no += 1
        if email_field:
            business_steps.append({"step_number": step_no, "description": "Enter a valid contact email address for the user."})
            step_no += 1
        if current_address:
            business_steps.append({"step_number": step_no, "description": "Provide the user's current residential address in a descriptive form."})
            step_no += 1
        if permanent_address:
            business_steps.append({"step_number": step_no, "description": "Provide the user's permanent address (if different from current)."})
            step_no += 1
        business_steps.append({"step_number": step_no, "description": "Submit the provided contact information for review."})
        step_no += 1
        business_steps.append({"step_number": step_no, "description": "Verify the page displays a submission summary that reflects the entered values."})

        # Expected results (business-focused)
        expected_results = []
        expected_results.append("Page loads and the contact form elements are visible and editable.")
        if name_field:
            expected_results.append("Entered full name is accepted and preserved in the submission summary.")
        if email_field:
            expected_results.append("Valid email is accepted and no client-side validation error is shown.")
        if current_address or permanent_address:
            expected_results.append("Address fields accept multi-line text and are shown verbatim in submission summary.")
        expected_results.append("After submission, a summary area presents the same values that were entered (suitable for text-contains assertions).")

        # Automation-ready steps
        automation_steps = []
        s = 1
        automation_steps.append({
            "step_number": s,
            "action": "navigate",
            "element_name": "Target Page",
            "locator_type": "url",
            "locator_value": self.url
        })
        s += 1

        # helper to pick locator
        def _locator(e: Dict[str, Any]) -> (str, str):
            if not e:
                return None, None
            if e.get('id'):
                return 'id', e.get('id')
            if e.get('name'):
                return 'name', e.get('name')
            if e.get('data-testid'):
                return 'data-testid', e.get('data-testid')
            # fallback to css selector using attribute if label exists
            if e.get('element_type') == 'textarea':
                tag = 'textarea'
            elif e.get('element_type') == 'button' or (e.get('element_type') and 'button' in e.get('element_type')):
                tag = 'button'
            else:
                tag = 'input'
            if e.get('id'):
                return 'css_selector', f"#{e.get('id')}"
            if e.get('name'):
                return 'css_selector', f"{tag}[name=\"{e.get('name')}\"]"
            return 'css_selector', tag

        # sample inputs
        sample_inputs = {
            'name': 'Alexandra Rivera',
            'email': 'alex.rivera+qa@example.com',
            'currentAddress': '123 Elm Street, Apt 4B\nSpringfield, IL 62704',
            'permanentAddress': 'PO Box 987\nShelbyville, IL 62565'
        }

        if name_field:
            lt, lv = _locator(name_field)
            automation_steps.append({
                'step_number': s,
                'action': 'enter_text',
                'element_name': name_field.get('element_name') or 'Full Name',
                'locator_type': lt,
                'locator_value': lv,
                'input_value': sample_inputs['name']
            })
            s += 1
        if email_field:
            lt, lv = _locator(email_field)
            automation_steps.append({
                'step_number': s,
                'action': 'enter_text',
                'element_name': email_field.get('element_name') or 'Email',
                'locator_type': lt,
                'locator_value': lv,
                'input_value': sample_inputs['email']
            })
            s += 1
        if current_address:
            lt, lv = _locator(current_address)
            automation_steps.append({
                'step_number': s,
                'action': 'enter_text',
                'element_name': current_address.get('element_name') or 'Current Address',
                'locator_type': lt,
                'locator_value': lv,
                'input_value': sample_inputs['currentAddress']
            })
            s += 1
        if permanent_address:
            lt, lv = _locator(permanent_address)
            automation_steps.append({
                'step_number': s,
                'action': 'enter_text',
                'element_name': permanent_address.get('element_name') or 'Permanent Address',
                'locator_type': lt,
                'locator_value': lv,
                'input_value': sample_inputs['permanentAddress']
            })
            s += 1

        # submit
        if submit_btn:
            lt, lv = _locator(submit_btn)
            automation_steps.append({
                'step_number': s,
                'action': 'click_element',
                'element_name': submit_btn.get('element_name') or 'Submit',
                'locator_type': lt,
                'locator_value': lv
            })
            s += 1
        else:
            # fallback: try to click by id 'submit' or button text
            automation_steps.append({
                'step_number': s,
                'action': 'click_element',
                'element_name': 'Submit',
                'locator_type': 'css_selector',
                'locator_value': '#submit'
            })
            s += 1

        # wait for output
        out_selector = None
        if output_container and output_container.get('id'):
            out_selector = f"#{output_container.get('id')}"
        else:
            out_selector = '#output'

        automation_steps.append({
            'step_number': s,
            'action': 'wait_for_element',
            'element_name': 'Submission Output Area',
            'locator_type': 'css_selector',
            'locator_value': out_selector,
            'selector': out_selector
        })
        s += 1

        # assertions: text-contains for each input
        if name_field:
            automation_steps.append({
                'step_number': s,
                'action': 'assert_text_contains',
                'element_name': 'Name in Output',
                'locator_type': 'css_selector',
                'locator_value': out_selector,
                'expected_value': sample_inputs['name'],
                'selector': out_selector
            })
            s += 1
        if email_field:
            automation_steps.append({
                'step_number': s,
                'action': 'assert_text_contains',
                'element_name': 'Email in Output',
                'locator_type': 'css_selector',
                'locator_value': out_selector,
                'expected_value': sample_inputs['email'],
                'selector': out_selector
            })
            s += 1
        if current_address:
            automation_steps.append({
                'step_number': s,
                'action': 'assert_text_contains',
                'element_name': 'Current Address in Output',
                'locator_type': 'css_selector',
                'locator_value': out_selector,
                'expected_value': sample_inputs['currentAddress'].split('\n')[0],
                'selector': out_selector
            })
            s += 1
        if permanent_address:
            automation_steps.append({
                'step_number': s,
                'action': 'assert_text_contains',
                'element_name': 'Permanent Address in Output',
                'locator_type': 'css_selector',
                'locator_value': out_selector,
                'expected_value': sample_inputs['permanentAddress'].split('\n')[0],
                'selector': out_selector
            })
            s += 1

        # final validation-check step
        if email_field:
            automation_steps.append({
                'step_number': s,
                'action': 'assert_no_validation_error',
                'element_name': 'Email Field Validation',
                'locator_type': 'id' if email_field.get('id') else ('name' if email_field.get('name') else 'data-testid'),
                'locator_value': email_field.get('id') or email_field.get('name') or email_field.get('data-testid'),
                'expected_value': 'no client-side validation message visible'
            })

        return {
            'scenario_description': f"Verify the page at {self.url} accepts contact information and reflects it in a submission summary.",
            'test_type': 'Functional',
            'page_analysis': self.analysis.get('page', {}).get('summary') or self.analysis.get('summary') or 'Auto-discovered contact form page.',
            'elements': self.elements,
            'mapping_data': {e.get('id') or e.get('name') or e.get('element_name'): f"User.{e.get('element_name')}" for e in self.elements},
            'user_intent': 'Provide valid contact details and verify they appear in the submission summary.',
            'business_steps': business_steps,
            'expected_results': expected_results,
            'automation_steps': automation_steps
        }


async def main():
    try:
        url = 'https://demoqa.com/text-box'
        result = await run_full_pipeline(url)
        print('SUCCESS', list(result.keys()))

        gen = ScenarioGenerator(result, url)
        output = gen.generate()

        backend_dir = __file__.rsplit('\\', 1)[0]
        scenario_path = backend_dir + '\\generated_scenario.json'
        testcase_path = backend_dir + '\\generated_testcase.json'

        # Write human-readable scenario + expected results
        with open(scenario_path, 'w', encoding='utf-8') as f:
            json.dump({
                'scenario_description': output['scenario_description'],
                'test_type': output['test_type'],
                'page_analysis': output['page_analysis'],
                'elements': output['elements'],
                'mapping_data': output['mapping_data'],
                'user_intent': output['user_intent'],
                'business_steps': output['business_steps'],
                'expected_results': output['expected_results']
            }, f, indent=2, ensure_ascii=False)

        # Write automation-ready testcase
        with open(testcase_path, 'w', encoding='utf-8') as f:
            json.dump(output['automation_steps'], f, indent=2, ensure_ascii=False)

        print('Generated:', scenario_path, testcase_path)

    except Exception:
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())
