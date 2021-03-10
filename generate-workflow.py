#!/usr/bin/env python3
# python3: Whee, type annotations!

# Script to generate .github/workflows/main.yml, since we need to generate many
# jobs with similar content and as far as we know, the workflow language has
# essentially no support for code reuse. :(

import textwrap
from typing import List, NamedTuple, Optional


class BenchmarkComponent(NamedTuple):
    name: str
    subdir: Optional[str] = None


class BenchmarkInfo(NamedTuple):
    name: str
    friendly_name: str
    dir_name: str
    build_cmds: str
    convert_extra: Optional[str] = None
    compile_converted_extra: Optional[str] = None
    components: Optional[List[BenchmarkComponent]] = None


ptrdist_components = ['anagram', 'bc', 'ft', 'ks', 'yacr2']

# The blank comments below stop YAPF from reformatting things in ways we don't
# want; large data literals are a known weakness of YAPF
# (https://github.com/google/yapf#why-does-yapf-destroy-my-awesome-formatting).

benchmarks = [

    # Vsftpd
    BenchmarkInfo('vsftpd', 'Vsftpd', 'vsftpd-3.0.3', 'bear make\n'),

    # PtrDist
    BenchmarkInfo(
        'ptrdist',
        'PtrDist',
        'ptrdist-1.1',
        textwrap.dedent(f'''\
        for i in {' '.join(ptrdist_components)} ; do \\
          (cd $i ; bear make LOCAL_CFLAGS="-D_ISOC99_SOURCE") \\
        done
        '''),
        compile_converted_extra='LOCAL_CFLAGS="-D_ISOC99_SOURCE"',
        components=[BenchmarkComponent(c, c) for c in ptrdist_components]),

    # LibArchive
    BenchmarkInfo(
        #
        'libarchive',
        'LibArchive',
        'libarchive-3.4.3',
        textwrap.dedent('''\
        cd build
        cmake -DCMAKE_C_FLAGS="-w -D_GNU_SOURCE" ..
        bear make
        '''),
        convert_extra=textwrap.dedent('''\
        --skip '/.*/(test|test_utils|tar|cat|cpio|examples|contrib|libarchive_fe)/.*' \\
        '''),
        components=[BenchmarkComponent('LibArchive', 'build')]),

    # Lua
    BenchmarkInfo(
        #
        'lua',
        'Lua',
        'lua-5.4.1',
        textwrap.dedent('''\
        bear make linux
        ( cd src ; \\
          clang-rename-10 -pl -i \\
            --qualified-name=main \\
            --new-name=luac_main \\
            luac.c )
        '''),
        compile_converted_extra='linux'),

    # LibTiff
    BenchmarkInfo(
        'libtiff',
        'LibTiff',
        'tiff-4.1.0',
        # Having compile_converted_project.sh pass
        # CC=${{env.builddir}}/bin/clang to `make` seems to be insufficient to
        # get it to use the Checked C compiler. (Surprisingly, for the other
        # CMake-based projects, it seems to be sufficient.) So just configure
        # the project with the Checked C compiler from the beginning.
        textwrap.dedent('''\
        cmake -DCMAKE_C_COMPILER=${{env.builddir}}/bin/clang -DCMAKE_C_FLAGS="-w" .
        bear make tiff
        ( cd tools ; \\
          for i in *.c ; do \\
            clang-rename-10 -pl -i \\
              --qualified-name=main \\
              --new-name=$(basename -s .c $i)_main $i ; \\
          done)
        '''),
        convert_extra=textwrap.dedent('''\
        --skip '/.*/tif_stream.cxx' \\
        --skip '.*/test/.*\.c' \\
        --skip '.*/contrib/.*\.c' \\
        '''),
        compile_converted_extra='tiff'),

    # Zlib
    BenchmarkInfo(
        #
        'zlib',
        'ZLib',
        'zlib-1.2.11',
        textwrap.dedent('''\
        mkdir build
        cd build
        cmake -DCMAKE_C_FLAGS="-w" ..
        bear make
        '''),
        convert_extra="--skip '/.*/test/.*' \\\n",
        components=[BenchmarkComponent('zlib', 'build')]),
]

HEADER = '''\
# This file is generated by generate-workflow.py. To update this file, update
# generate-workflow.py instead and re-run it. Some things in this file are
# explained by comments in generate-workflow.py.

name: 3C benchmark tests

on:
  # Run every day at 3:00 AM EDT (i.e., 7 am UTC)
  schedule:
    - cron: "0 7 * * *"
  workflow_dispatch:
    inputs:
      branch:
        description: "Branch or commit ID of correctcomputation/checkedc-clang to run workflow on"
        required: true
        default: "main"

env:
  benchmark_tar_dir: "/home/github/checkedc-benchmarks"
  builddir: "${{github.workspace}}/b/ninja"
  benchmark_conv_dir: "${{github.workspace}}/benchmark_conv"
  branch_for_scheduled_run: "main"
  include_dir: "${{github.workspace}}/depsfolder/checkedc-clang/llvm/projects/checkedc-wrapper/checkedc/include"
  port_tools: "${{github.workspace}}/depsfolder/checkedc-clang/clang/tools/3c/utils/port_tools"

jobs:

  # Cleanup files left behind by prior runs
  clean:
    name: Clean
    runs-on: self-hosted
    steps:
      - name: Clean
        run: |
          rm -rf ${{env.benchmark_conv_dir}}
          mkdir -p ${{env.benchmark_conv_dir}}
          rm -rf ${{env.builddir}}
          mkdir -p ${{env.builddir}}
          rm -rf ${{github.workspace}}/depsfolder
          mkdir -p ${{github.workspace}}/depsfolder

  # Clone and build 3c and clang
  # (clang is needed to test compilation of converted benchmarks.)
  build_3c:
    name: Build 3c and clang
    needs: clean
    runs-on: self-hosted
    steps:
      - name: Branch or commit ID
        run: echo "${{ github.event.inputs.branch || env.branch_for_scheduled_run }}"
      - name: Checkout our repository
        run: |
          git init ${{github.workspace}}/depsfolder/checkedc-clang
          cd ${{github.workspace}}/depsfolder/checkedc-clang
          git remote add origin https://github.com/correctcomputation/checkedc-clang
          git fetch --depth 1 origin "${{ github.event.inputs.branch || env.branch_for_scheduled_run }}"
          git checkout FETCH_HEAD
          git clone --depth 1 https://github.com/microsoft/checkedc ${{github.workspace}}/depsfolder/checkedc-clang/llvm/projects/checkedc-wrapper/checkedc

      - name: Build 3c and clang
        run: |
          cd ${{env.builddir}}
          cmake -G Ninja \\
            -DLLVM_TARGETS_TO_BUILD=X86 \\
            -DCMAKE_BUILD_TYPE="Debug" \\
            -DLLVM_OPTIMIZED_TABLEGEN=ON \\
            -DLLVM_USE_SPLIT_DWARF=ON \\
            -DLLVM_ENABLE_PROJECTS="clang" \\
            ${{github.workspace}}/depsfolder/checkedc-clang/llvm
          # -l 36: Try not to overload gamera. Hopefully this will use all 36
          # hyperthreads when nothing else is running and automatically scale
          # back when other jobs are running. TODO: Better solution?
          ninja -l 36 3c clang
          chmod -R 777 ${{github.workspace}}/depsfolder
          chmod -R 777 ${{env.builddir}}

  # Run Test for 3C
  test_3c:
    name: 3C regression tests
    needs: build_3c
    runs-on: self-hosted
    steps:
      - name: 3C regression tests
        run: |
          cd ${{env.builddir}}
          ninja check-3c

  # Convert our benchmark programs
'''


class Step(NamedTuple):
    name: str
    run: str  # Trailing newline but not blank line

    def __str__(self):
        part1 = textwrap.dedent(f'''\
        - name: {self.name}
          run: |
        ''')
        part2 = textwrap.indent(self.run, 4 * ' ')
        return textwrap.indent(part1 + part2, 6 * ' ')


with open('.github/workflows/main.yml', 'w') as out:
    out.write(HEADER)
    for binfo in benchmarks:
        for alltypes in (False, True):
            at_dir = ('${{env.benchmark_conv_dir}}/' +
                      ('alltypes' if alltypes else 'no-alltypes'))
            at_job = 'alltypes' if alltypes else 'no_alltypes'
            at_job_friendly = '-alltypes' if alltypes else 'no -alltypes'
            convert_extra = binfo.convert_extra or ''
            compile_converted_extra = (' ' + binfo.compile_converted_extra if
                                       binfo.compile_converted_extra is not None
                                       else '')
            # Python argparse thinks `-extra-3c-arg -alltypes` is two options
            # rather than an option with an argument.
            at_flag = '-extra-3c-arg=-alltypes \\\n' if alltypes else ''
            at_ignore_step = ' (ignore failure)' if alltypes else ''
            at_ignore_code = ' || true' if alltypes else ''

            out.write(f'''\

  test_{binfo.name}_{at_job}:
    name: Test {binfo.friendly_name} ({at_job_friendly})
    needs: build_3c
    runs-on: self-hosted
    steps:
''')

            full_build_cmds = textwrap.dedent(f'''\
            mkdir -p {at_dir}
            cd {at_dir}
            tar -xvzf ${{{{env.benchmark_tar_dir}}}}/{binfo.dir_name}.tar.gz
            cd {binfo.dir_name}
            ''') + binfo.build_cmds

            steps = [Step('Build ' + binfo.friendly_name, full_build_cmds)]

            components = binfo.components
            if components is None:
                components = [BenchmarkComponent(binfo.friendly_name)]

            for component in components:
                component_dir = f'{at_dir}/{binfo.dir_name}'
                if component.subdir is not None:
                    component_dir += '/' + component.subdir

                # yapf: disable
                convert_flags = textwrap.indent(
                    convert_extra +
                    '--includeDir ${{env.include_dir}} \\\n' +
                    '-p ${{env.builddir}}/bin/3c \\\n' +
                    at_flag +
                    '-pr .\n',
                    2 * ' ')
                # yapf: enable
                steps.append(
                    Step(
                        'Convert ' + component.name,
                        textwrap.dedent(f'''\
                        cd {component_dir}
                        ${{{{env.port_tools}}}}/convert_project.py \\
                        ''') + convert_flags))

                steps.append(
                    Step(
                        'Build converted ' + component.name + at_ignore_step,
                        textwrap.dedent(f'''\
                        cd {component_dir}
                        ${{{{env.port_tools}}}}/compile_converted_project.sh \\
                          ${{{{env.builddir}}}}/bin/clang{compile_converted_extra}{at_ignore_code}
                        ''')))

            # We want blank lines between steps but not after the last step of
            # the last benchmark.
            out.write('\n'.join(str(s) for s in steps))