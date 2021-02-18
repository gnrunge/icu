# © 2021 and later: Unicode, Inc. and others.
# License & terms of use: http://www.unicode.org/copyright.html

"""Executes uconfig variations check.

See
http://site.icu-project.org/processes/release/tasks/healthy-code#TOC-Test-uconfig.h-variations
for more information.
"""

import os
import re
import subprocess
import sys

excluded_unit_test_flags = ['UCONFIG_NO_CONVERSION', 'UCONFIG_NO_FILE_IO'];

def ReadFile(filename):
    """Reads a file and returns the content of the file

    Args:
      command: string with the filename.

    Returns:
      Content of file.
    """

    with open(filename, 'r') as file_handle:
      return file_handle.read()

def RunCmd(command):
    """Execute the command, returns output and exit code, writes output to log

    Args:
      command: string with the command.

    Returns: stdout and exit code of command execution.
    """

    command += ' >> uconfig_test.log 2>&1'
    p = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, close_fds=True)
    stdout, _ = p.communicate()
    return stdout, p.returncode

def SetUpICU():
    """Configuration, installation of ICU4C."""

    _, exit_code = RunCmd('rm -rf /tmp/icu_cnfg')
    print('Exit code rm: %d\n' % exit_code)
    _, exit_code= RunCmd('mkdir /tmp/icu_cnfg')
    print('Exit code mkdir: %d\n' % exit_code)
    out, exit_code = RunCmd('runConfigureICU Linux --prefix=/tmp/icu_cnfg')
    print('output:\n')
    print(out)
    os.system('cat uconfig_test.log')
    if exit_code != 0:
        print('ICU4C configuration failed!')
        sys.exit(-1)

    log, _ = RunCmd('cat uconfig_test.log')
    print('log:\n')
    print(log)

    _, exit_code = RunCmd('make -j2 install')
    if exit_code != 0:
        print('make install failed!')
        sys.exit(-1)
    # The header test is set up in a way that it uses uconfig.h in /tmp/icu_cnfg
    # while the ICU4C unit tests uses common/unicode/uconfig.h. Set a link.
    RunCmd('rm /tmp/icu_cnfg/include/unicode/uconfig.h')
    os.symlink(os.path.abspath('common/unicode/uconfig.h'),
               '/tmp/icu_cnfg/include/unicode/uconfig.h')

def ExtractUConfigNoXXX(uconfig_file):
    """Parses uconfig.h and returns a list of UCONFIG_NO_XXX labels.
    Initializes test result structure.

    Args:
      uconfig_file: common/unicode/uconfig.h as string.

    Returns:
      List of all UCONFIG_NO_XXX flags found in uconfig.h, initialized test
      result structure.
    """

    uconfig_no_flags_all = []
    test_results = {}
    uconfig_no_regex = r'UCONFIG_NO_[A-Z_]*'

    for uconfig_no_flag in re.finditer(uconfig_no_regex, uconfig_file):
        if uconfig_no_flag.group(0) not in uconfig_no_flags_all:
            uconfig_no_flags_all.append(uconfig_no_flag.group(0))

    test_results = {f: {'unit_test': False, 'hdr_test': False} for f in uconfig_no_flags_all}
    test_results['all_flags'] = {'unit_test': False, 'hdr_test' : False}

    return uconfig_no_flags_all, test_results

def EnableUConfigNo(uconfig_file, uconfig_no_flag):
    """Sets the uconfig_no_flag in common/unicode/uconfig.h file.

    Args:
      uconfig_file: common/unicode/uconfig.h as string.
      uconfig_no_flag: flags that is to be set to 1.

    Returns:
      uconfig.h with flag set to 1
    """

    uconfig_no_def_regex = r'(?m)#ifndef %s\n#\s+define %s\s+0\n#endif$' % (
        uconfig_no_flag, uconfig_no_flag)
    uconfig_no_def_match = re.search(uconfig_no_def_regex, uconfig_file)
    if not uconfig_no_def_match:
        print('No definition for flag %s found!\n' % uconfig_no_flag)
        sys.exit(-1)
    uconfig_no_def = uconfig_no_def_match.group(0)
    set_uconfig_no_def = uconfig_no_def.replace(' 0\n', ' 1\n')
    set_in_uconfig_file = uconfig_file.replace(uconfig_no_def, set_uconfig_no_def)

    return set_in_uconfig_file

def main():
    os.chdir('icu4c/source')
    orig_uconfig_file = ReadFile('common/unicode/uconfig.h')

    all_uconfig_no_flags, test_results = ExtractUConfigNoXXX(orig_uconfig_file)
    if not all_uconfig_no_flags:
        print('No UCONFIG_NO_XXX flags found!\n')
        sys.exit(-1)
    SetUpICU()

    # Iterate over all flags, set each individually one in uconfig.h and
    # execute ICU4C unit tests and header test.
    for uconfig_no in all_uconfig_no_flags:
        with open('common/unicode/uconfig.h', 'w') as file_handle:
            file_handle.write(EnableUConfigNo(orig_uconfig_file, uconfig_no))
        RunCmd('make clean')

        # Run ICU4C unit tests, except for the excluded flags.
        if uconfig_no not in excluded_unit_test_flags:
            unit_test_result, exit_code = RunCmd('make -j2 check')
            if exit_code == 0:
                print('Unit tests with %s set to 1 pass!' % uconfig_no)
                test_results[uconfig_no]['unit_test'] = True
            else:
                print('Unit tests with %s set to 1 fail!\n' % uconfig_no)
                print('Test output:\n')
                print(unit_test_result)
                test_results[uconfig_no]['unit_test'] = False

        # Run header test for all flags.
        hdr_test_result, exit_code = RunCmd(
            'PATH=/tmp/icu_cnfg/bin:$PATH make -C test/hdrtst check')
        if exit_code == 0:
            print('Header tests with %s set to 1 pass!' % uconfig_no)
            test_results[uconfig_no]['hdr_test'] = True
        else:
            print('Header tests with %s set to 1 fail!' % uconfig_no)
            print('Test output:\n')
            print(unit_test_result)
            test_results[uconfig_no]['unit_test'] = False

    # Run unit tests with all flags set to '1' except for excluded flags.
    uconfig_no_all = orig_uconfig_file
    for uconfig_no in all_uconfig_no_flags:
        if uconfig_no not in excluded_unit_test_flags:
            uconfig_no_all = EnableUConfigNo(uconfig_no_all, uconfig_no)
    with open('common/unicode/uconfig.h', 'w') as file_handle:
        file_handle.write(uconfig_no_all)
    RunCmd('make clean')

    unit_test_result_all, exit_code = RunCmd('make -j2 check')
    if exit_code == 0:
        print('Unit tests with all flags set to 1 pass!')
        test_results['all_flags']['unit_test'] = True
    else:
        print('Unit tests with all flags set to 1 fail!\n')
        print('Test output:\n')
        print(unit_test_result)
        test_results['all_flags']['unit_test'] = False

    # Run header tests with all flags set to '1'.
    hdr_test_result_all, exit_code = RunCmd(
            'PATH=/tmp/icu_cnfg/bin:$PATH make -C test/hdrtst check')
    if exit_code == 0:
        print('Header tests with %s set to 1 pass!' % uconfig_no)
        test_results['all_flags']['hdr_test'] = True
    else:
        print('Header tests with %s set to 1 fail!' % uconfig_no)
        print('Test output:\n')
        print(unit_test_result)
        test_results['all_flags']['hdr_test'] = False

    # Review test results and report any failures.
    outcome = 0
    print('Summary:\n')
    for uconfig_no in all_uconfig_no_flags:
        if uconfig_no not in excluded_unit_test_flags:
            if test_results[uconfig_no]['unit_test'] == False:
                outcome = -1
                print('%s: unit tests fail' % uconfig_no)
        if test_results[uconfig_no]['hdr_test'] == False:
            outcome = -1
            print('%s: header tests fails' % uconfig_no)
    if test_results['all_flags']['unit_test'] == False:
        outcome = -1
        print('all flags to 1: unit tests fail!')
    if test_results['all_flags']['hdr_test'] == False:
        outcome = -1
        print('all flags to 1: header tests fail!')
    if outcome == 0:
        print('Tests pass for all uconfig variations!')
    sys.exit(outcome)

if __name__ == '__main__':
  main()
