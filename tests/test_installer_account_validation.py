"""Run the actual account-form validator with DOM field values, without a browser."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallerAccountValidationTests(unittest.TestCase):
    def test_form_rejects_protocol_delimiters_and_preserves_valid_passwords(self):
        result = subprocess.run(
            ["node", "-", str(ROOT / "installer/ui/app.js")],
            input=r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const app = fs.readFileSync(process.argv[2], 'utf8');
const source = 'function validate()' + app.split('function validate()')[1]
  .split('function suggestedUsername')[0] + '\nvalidate()';
const defaults = {hostname:'lyra-os', username:'lyra', 'full-name':'María D’Ávila, 李',
  password:'valid-password', 'password-confirm':'valid-password'};
const cases = [
  ['password', 'valid-pass\nroot:other-pass', 'validation.invalidPassword'],
  ['password', 'valid-pass\r\nroot:other-pass', 'validation.invalidPassword'],
  ['password', 'valid-pass\0suffix', 'validation.invalidPassword'],
  ['password', 'a'.repeat(8186), 'validation.passwordTooLong'],
  ['password', 'é'.repeat(4093), 'validation.passwordTooLong'],
  ['password', '🔑'.repeat(4), 'validation.passwordTooShort'],
  ['full-name', 'Name:extra-field', 'validation.invalidFullName'],
  ['full-name', 'Name\nextra-record', 'validation.invalidFullName'],
  ['full-name', 'Name\0truncated', 'validation.invalidFullName'],
  ['full-name', 'a'.repeat(131072), 'validation.invalidFullName'],
  ['full-name', '   ', 'validation.fullNameRequired'],
  ['username', 'root', 'validation.invalidUsername'],
  ['password-confirm', 'different-password', 'validation.passwordMismatch'],
  ...['  pass:word  ', 'quotes\'"\\$word', 'é🔑senha-segura', 'password\rdata',
     'password\u2028data', '🔑'.repeat(8), 'a'.repeat(8185)]
     .map(password => ['password', password, '']),
  ['full-name', 'a'.repeat(131071), ''],
];
for (const [field, value, expected] of cases) {
  const values = {...defaults, [field]:value};
  if (field === 'password') values['password-confirm'] = value;
  const fields = Object.fromEntries(Object.entries(values).map(([id,value]) => ['#'+id, {value}]));
  fields['#validation'] = {textContent:''};
  const result = vm.runInNewContext(source, {
    TextEncoder, document:{querySelector:id => fields[id]}, i18n:{t:key=>key}
  });
  assert.equal(result, expected === '');
  // Exact keys also prove the error display never echoes the supplied data.
  assert.equal(fields['#validation'].textContent, expected);
}
console.log(cases.length + ' account form cases passed');
""",
            text=True, capture_output=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
