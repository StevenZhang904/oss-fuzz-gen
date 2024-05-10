#!/usr/bin/env python3
# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Utilities for generating builder scripts for a GitHub repository."""

import os
import subprocess
from abc import abstractmethod
from typing import Any, Dict, Iterator, List, Tuple

import manager


############################################################
#### Logic for auto building a given source code folder ####
############################################################
class AutoBuildContainer:

  def __init__(self):
    self.list_of_commands = []
    self.heuristic_id = ''


class AutoBuildBase:
  """Base class for auto builders."""

  def __init__(self):
    self.matches_found = {}

  @abstractmethod
  def steps_to_build(self) -> Iterator[AutoBuildContainer]:
    """Yields AutoBuildContainer objects."""

  def match_files(self, file_list):
    """Matches files needed for the build heuristic."""
    for fi in file_list:
      base_file = os.path.basename(fi)
      for key, val in self.matches_found.items():
        if base_file == key:
          val.append(fi)

  def is_matched(self):
    """Returns True if the build heuristic found matching files."""
    for matches in self.matches_found:
      if len(matches) == 0:
        return False
    return True


class PureCFileCompiler(AutoBuildBase):
  """Builder for compiling .c files direcetly in root repo dir."""

  def __init__(self):
    super().__init__()
    self.matches_found = {
        '.c': [],
    }

  def match_files(self, file_list):
    """Matches files needed for the build heuristic."""
    for fi in file_list:
      for key, val in self.matches_found.items():
        if fi.endswith(key) and 'test' not in fi and 'example' not in fi:
          print('Adding %s' % (fi))
          # Remove the first folder as that is "this" dir.
          path_to_add = '/'.join(fi.split('/')[1:])
          val.append(path_to_add)

  def steps_to_build(self) -> Iterator[AutoBuildContainer]:
    build_container = AutoBuildContainer()
    build_container.list_of_commands = [
        '''for file in "%s"; do
  $CC $CFLAGS -c ${file}
done

rm -f ./test*.o
llvm-ar rcs libfuzz.a *.o
''' % (' '.join(self.matches_found['.c']))
    ]
    build_container.heuristic_id = self.name + '1'
    print(build_container.list_of_commands[0])
    yield build_container

  @property
  def name(self):
    return 'pureCFileCompiler'


class PureCFileCompilerFind(AutoBuildBase):
  """Builder for compiling .c files direcetly in root repo dir, using find."""

  def __init__(self):
    super().__init__()
    self.matches_found = {
        '.c': [],
    }

  def match_files(self, file_list):
    """Matches files needed for the build heuristic."""
    for fi in file_list:
      for key, val in self.matches_found.items():
        if fi.endswith(key):
          val.append(fi)

  def steps_to_build(self) -> Iterator[AutoBuildContainer]:
    build_container = AutoBuildContainer()
    build_container.list_of_commands = [
        '''find . -name "*.c" -exec $CC $CFLAGS -I./src -c {} \\;
find . -name "*.o" -exec cp {} . \\;

rm -f ./test*.o
llvm-ar rcs libfuzz.a *.o
'''
    ]
    build_container.heuristic_id = self.name + '1'
    yield build_container

  @property
  def name(self):
    return 'pureCFileCompilerFind'


class PureMakefileScanner(AutoBuildBase):
  """Auto builder for pure Makefile projects, only relying on "make"."""

  def __init__(self):
    super().__init__()
    self.matches_found = {
        'Makefile': [],
    }

  def steps_to_build(self) -> Iterator[AutoBuildContainer]:
    build_container = AutoBuildContainer()
    build_container.list_of_commands = ['make']
    build_container.heuristic_id = self.name + '1'
    yield build_container

  @property
  def name(self):
    return 'make'


class PureMakefileScannerWithPThread(AutoBuildBase):
  """Auto builder for pure Makefile projects, only relying on "make"."""

  def __init__(self):
    super().__init__()
    self.matches_found = {
        'Makefile': [],
    }

  def steps_to_build(self) -> Iterator[AutoBuildContainer]:
    build_container = AutoBuildContainer()
    build_container.list_of_commands = [
        'export CXXFLAGS="${CXXFLAGS} -lpthread"', 'make'
    ]
    build_container.heuristic_id = self.name + '1'
    yield build_container

  @property
  def name(self):
    return 'make'


class PureMakefileScannerWithSubstitutions(AutoBuildBase):
  """Auto builder for pure Makefile projects with substitions."""

  def __init__(self):
    super().__init__()
    self.matches_found = {
        'Makefile': [],
    }

  def steps_to_build(self) -> Iterator[AutoBuildContainer]:
    build_container = AutoBuildContainer()
    # The following substitutes varioues patterns of overwriting of compilers
    # which happens in some build files. Patterns of Werror are also suppressed
    # by converting them to Wno-error.
    build_container.list_of_commands = [
        'sed -i \'s/-Werror/-Wno-error/g\' ./Makefile',
        'sed -i \'s/CC=/#CC=/g\' ./Makefile',
        'sed -i \'s/CXX=/#CXX=/g\' ./Makefile',
        'sed -i \'s/CC =/#CC=/g\' ./Makefile',
        'sed -i \'s/CXX =/#CXX=/g\' ./Makefile', 'make V=1 || true'
    ]
    build_container.heuristic_id = self.name + '1'
    yield build_container

  @property
  def name(self):
    return 'makeWithSubstitutions'


class AutoRefConfScanner(AutoBuildBase):
  """Auto-builder for patterns of "autoreconf fi; ./configure' make"""

  def __init__(self):
    super().__init__()
    self.matches_found = {
        'configure.ac': [],
        'Makefile.am': [],
    }

  def steps_to_build(self):
    cmds_to_exec_from_root = ['autoreconf -fi', './configure', 'make']
    build_container = AutoBuildContainer()
    build_container.list_of_commands = cmds_to_exec_from_root
    build_container.heuristic_id = self.name + '1'
    yield build_container

  @property
  def name(self):
    return 'autogen'


class RawMake(AutoBuildBase):
  """Similar to PureMake but also adds option for "make test". This is useful
  to trigger more Fuzz Introspector analysis in the project."""

  def __init__(self):
    super().__init__()
    self.matches_found = {
        'Makefile': [],
    }

  def steps_to_build(self):
    cmds_to_exec_from_root = ['make']
    #yield cmds_to_exec_from_root
    build_container = AutoBuildContainer()
    build_container.list_of_commands = cmds_to_exec_from_root
    build_container.heuristic_id = self.name + '1'
    yield build_container

    build_container2 = AutoBuildContainer()
    build_container2.list_of_commands = cmds_to_exec_from_root + ['make test']
    build_container2.heuristic_id = self.name + '1'
    yield build_container2

  @property
  def name(self):
    return 'RawMake'


class AutogenScanner(AutoBuildBase):
  """Auto builder for projects relying on "autoconf; autoheader."""

  def __init__(self):
    super().__init__()
    self.matches_found = {
        'configure.ac': [],
        'Makefile': [],
    }

  def steps_to_build(self):
    cmds_to_exec_from_root = ['autoconf', 'autoheader', './configure', 'make']
    #yield cmds_to_exec_from_root
    build_container = AutoBuildContainer()
    build_container.list_of_commands = cmds_to_exec_from_root
    build_container.heuristic_id = self.name + '1'
    yield build_container

  @property
  def name(self):
    return 'autogen'


class AutogenConfScanner(AutoBuildBase):
  """Auto builder for projects relying on "autoconf; autoheader."""

  def __init__(self):
    super().__init__()
    self.matches_found = {
        'configure.ac': [],
        'Makefile': [],
    }

  def steps_to_build(self):
    cmds_to_exec_from_root = ['./configure', 'make']
    #yield cmds_to_exec_from_root
    build_container = AutoBuildContainer()
    build_container.list_of_commands = cmds_to_exec_from_root
    build_container.heuristic_id = self.name + '1'
    yield build_container

  @property
  def name(self):
    return 'autogen-ConfMake'


class CMakeScanner(AutoBuildBase):
  """Auto builder for CMake projects."""

  def __init__(self):
    super().__init__()
    self.matches_found = {
        'CMakeLists.txt': [],
    }

    self.cmake_options = set()

  def match_files(self, file_list: List[str]) -> None:
    for fi in file_list:
      base_file = os.path.basename(fi)
      for key, matches in self.matches_found.items():
        if base_file == key:
          matches.append(fi)

          with open(fi, 'r') as f:
            content = f.read()
          for line in content.split('\n'):
            if 'option(' in line:
              option = line.split('option(')[1].split(' ')[0]
              self.cmake_options.add(option)

    if len(self.cmake_options) > 0:
      print('Options:')
      for option in self.cmake_options:
        print('%s' % (option))

  def steps_to_build(self):
    # When we are running this, we are confident there are
    # some heuristics that match what is needed for cmake builds.
    # At this point, we will also scan for potential options
    # in the cmake files, such as:
    # - options related to shared libraries.
    # - options related to which packags need installing.
    cmds_to_exec_from_root = [
        'mkdir fuzz-build',
        'cd fuzz-build',
        'cmake -DCMAKE_VERBOSE_MAKEFILE=ON ../',
        'make V=1 || true',
    ]
    build_container = AutoBuildContainer()
    build_container.list_of_commands = cmds_to_exec_from_root
    build_container.heuristic_id = self.name + '1'
    yield build_container

    cmake_opts = [
        '-DCMAKE_VERBOSE_MAKEFILE=ON', '-DCMAKE_CXX_COMPILER=$CXX',
        '-DCMAKE_CXX_FLAGS=\"$CXXFLAGS\"'
    ]

    opt1 = [
        'mkdir fuzz-build',
        'cd fuzz-build',
        'cmake %s ../' % (' '.join(cmake_opts)),
        'make V=1 || true',
    ]
    build_container2 = AutoBuildContainer()
    build_container2.list_of_commands = opt1
    build_container2.heuristic_id = self.name + '2'
    yield build_container2

    # Force static libraryes
    opt_static = [
        'mkdir fuzz-build',
        'cd fuzz-build',
        'cmake %s ../' % (' '.join(cmake_opts)),
        'sed -i \'s/SHARED/STATIC/g\' ../CMakeLists.txt',
        'make V=1 || true',
    ]
    build_container_static = AutoBuildContainer()
    build_container_static.list_of_commands = opt_static
    build_container_static.heuristic_id = self.name + 'static'
    yield build_container_static

    # Look for options often used for disabling dynamic shared libraries.
    option_values = []
    for option in self.cmake_options:
      if 'BUILD_SHARED_LIBS' == option:
        option_values.append('-D%s=OFF' % (option))
      elif 'BUILD_STATIC' == option:
        option_values.append('-D%s=ON' % (option))
      elif 'BUILD_SHARED' == option:
        option_values.append('-D%s=OFF' % (option))
      elif 'ENABLE_STATIC' == option:
        option_values.append('-D%s=ON' % (option))

    if len(option_values) > 0:
      option_string = ' '.join(option_values)
      cmake_default_options = [
          '-DCMAKE_VERBOSE_MAKEFILE=ON', '-DCMAKE_CXX_COMPILER=$CXX',
          '-DCMAKE_CXX_FLAGS=\"$CXXFLAGS\"'
      ]
      bopt = [
          'mkdir fuzz-build',
          'cd fuzz-build',
          'cmake %s %s ../' % (' '.join(cmake_default_options), option_string),
          'make V=1',
      ]
      build_container3 = AutoBuildContainer()
      build_container3.list_of_commands = bopt
      build_container3.heuristic_id = self.name + '3'
      yield build_container3

    # Build tests in-case
    # Look for options often used for disabling dynamic shared libraries.
    option_values = []
    for option in self.cmake_options:
      if 'BUILD_SHARED_LIBS' == option:
        option_values.append('-D%s=OFF' % (option))
      elif 'BUILD_STATIC' == option:
        option_values.append('-D%s=ON' % (option))
      elif 'BUILD_SHARED' == option:
        option_values.append('-D%s=OFF' % (option))
      elif 'ENABLE_STATIC' == option:
        option_values.append('-D%s=ON' % (option))
      elif 'BUILD_TESTS' in option:
        option_values.append('-D%s=ON' % (option))

    if len(option_values) > 0:
      option_string = ' '.join(option_values)
      cmake_default_options = [
          '-DCMAKE_VERBOSE_MAKEFILE=ON', '-DCMAKE_CXX_COMPILER=$CXX',
          '-DCMAKE_CXX_FLAGS=\"$CXXFLAGS\"'
      ]
      bopt = [
          'mkdir fuzz-build',
          'cd fuzz-build',
          'cmake %s %s ../' % (' '.join(cmake_default_options), option_string),
          'make V=1',
      ]
      build_container4 = AutoBuildContainer()
      build_container4.list_of_commands = bopt
      build_container4.heuristic_id = self.name + '3'
      yield build_container4

  @property
  def name(self):
    return 'cmake'


def match_build_heuristics_on_folder(abspath_of_target: str):
  """Yields AutoBuildContainer objects.

  Traverses the files in the target folder. Uses the file list as input to
  auto build heuristics, and for each heuristic will yield any of the
  build steps that are deemed matching."""
  all_files = manager.get_all_files_in_path(abspath_of_target)
  all_checks = [
      AutogenConfScanner(),
      PureCFileCompiler(),
      PureCFileCompilerFind(),
      PureMakefileScanner(),
      PureMakefileScannerWithPThread(),
      PureMakefileScannerWithSubstitutions(),
      AutogenScanner(),
      AutoRefConfScanner(),
      CMakeScanner(),
      RawMake(),
  ]

  for scanner in all_checks:
    scanner.match_files(all_files)
    if scanner.is_matched():
      print('Matched: %s' % (scanner.name))
      for auto_build_gen in scanner.steps_to_build():
        yield auto_build_gen


def get_all_binary_files_from_folder(path: str) -> Dict[str, List[str]]:
  """Extracts binary artifacts from a list of files, based on file suffix."""
  all_files = manager.get_all_files_in_path(path, path)

  executable_files = {'static-libs': [], 'dynamic-libs': [], 'object-files': []}
  for fil in all_files:
    if fil.endswith('.o'):
      executable_files['object-files'].append(fil)
    if fil.endswith('.a'):
      executable_files['static-libs'].append(fil)
    if fil.endswith('.so'):
      executable_files['dynamic-libs'].append(fil)
  return executable_files


def wrap_build_script(test_dir: str, build_container: AutoBuildContainer,
                      abspath_of_target: str) -> str:
  build_script = '#!/bin/bash\n'
  build_script += 'rm -rf /%s\n' % (test_dir)
  build_script += 'cp -rf %s %s\n' % (abspath_of_target, test_dir)
  build_script += 'cd %s\n' % (test_dir)
  for cmd in build_container.list_of_commands:
    build_script += cmd + '\n'

  return build_script


def convert_build_heuristics_to_scripts(
    all_build_suggestions: List[AutoBuildContainer], testing_base_dir: str,
    abspath_of_target: str) -> List[Tuple[str, str, AutoBuildContainer]]:
  """Convert Auto build containers into bash scripts."""
  all_build_scripts = []
  for idx, build_suggestion in enumerate(all_build_suggestions):
    test_dir = os.path.abspath(
        os.path.join(os.getcwd(), testing_base_dir + str(idx)))
    build_script = wrap_build_script(test_dir, build_suggestion,
                                     abspath_of_target)
    all_build_scripts.append((build_script, test_dir, build_suggestion))
  return all_build_scripts


def extract_build_suggestions(
    target_dir, testing_base_dir) -> List[Tuple[str, str, AutoBuildContainer]]:
  """Statically create suggested build scripts for a project."""
  # Get all of the build heuristics
  all_build_suggestions: List[AutoBuildContainer] = list(
      match_build_heuristics_on_folder(target_dir))
  print('Found %d possible build suggestions' % (len(all_build_suggestions)))
  #all_build_suggestions = all_build_suggestions[:2]
  for build_suggestion in all_build_suggestions:
    print(f'- {build_suggestion.heuristic_id}')

  # Convert the build heuristics into build scripts
  all_build_scripts = convert_build_heuristics_to_scripts(
      all_build_suggestions, testing_base_dir, target_dir)
  return all_build_scripts


def raw_build_evaluation(
    all_build_scripts: List[Tuple[str, str, AutoBuildContainer]],
    initial_executable_files: Dict[str, List[str]]) -> Dict[str, Any]:
  """Run each of the build scripts and extract any artifacts build by them."""
  build_results = {}
  for build_script, test_dir, build_suggestion in all_build_scripts:
    print(f'Evaluating build heuristic {build_suggestion.heuristic_id}')
    with open('/src/build.sh', 'w') as bf:
      bf.write(build_script)
    try:
      subprocess.check_call('compile',
                            shell=True,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
      pass

    # Identify any binary artifacts built that weren't there prior
    # to running the build.
    binary_files_build = get_all_binary_files_from_folder(test_dir)

    new_binary_files = {
        'static-libs': [],
        'dynamic-libs': [],
        'object-files': []
    }
    for key, bfiles in binary_files_build.items():
      for bfile in bfiles:
        if bfile not in initial_executable_files[key]:
          new_binary_files[key].append(bfile)

    print(f'Static libs found {new_binary_files}')
    # binary_files_build['static-libs'])
    build_results[test_dir] = {
        'build-script': build_script,
        'executables-build': binary_files_build,
        'auto-build-setup': (build_script, test_dir, build_suggestion)
    }
  return build_results