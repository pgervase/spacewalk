#
# Copyright (c) 2008 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public License,
# version 2 (GPLv2). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. You should have received a copy of GPLv2
# along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.
#
# Red Hat trademarks are not licensed under GPLv2. No permission is
# granted to use or replicate Red Hat trademarks that are incorporated
# in this software or its documentation.

""" Code for building Spacewalk/Satellite tarballs, srpms, and rpms. """

import os
import re
import sys
import commands

from spacewalk.releng.common import run_command, find_git_root, \
        check_tag_exists, debug, error_out, find_spec_file, \
        get_project_name, get_relative_project_dir, get_build_commit, \
        get_git_head_commit, create_tgz

DEFAULT_KOJI_OPTS = "build --nowait"

class Builder(object):
    """
    Parent builder class.

    Includes functionality for a standard Spacewalk package build. Packages
    which require other unusual behavior can subclass this to inject the
    desired behavior.
    """

    def __init__(self, name=None, version=None, tag=None, build_dir=None,
            pkg_config=None, global_config=None, dist=None, test=False,
            offline=False):

        self.git_root = find_git_root()
        self.rel_eng_dir = os.path.join(self.git_root, "rel-eng")

        self.project_name = name
        self.build_tag = tag
        self.build_version = version
        self.dist = dist
        self.test = test
        self.global_config = global_config
        self.offline=offline
        self.no_cleanup = False

        self.rpmbuild_basedir = build_dir
        self.display_version = self._get_display_version()

        self.git_commit_id = get_build_commit(tag=self.build_tag, 
                test=self.test)
        self.project_name_and_sha1 = "%s-%s" % (self.project_name,
                self.git_commit_id)

        self.relative_project_dir = get_relative_project_dir(
                project_name=self.project_name, commit=self.git_commit_id)

        tgz_base = self._get_tgz_name_and_ver()
        self.tgz_filename = tgz_base + ".tar.gz"
        self.tgz_dir = tgz_base

        temp_dir = "rpmbuild-%s" % self.project_name_and_sha1
        self.rpmbuild_dir = os.path.join(self.rpmbuild_basedir, temp_dir)
        self.rpmbuild_sourcedir = os.path.join(self.rpmbuild_dir, "SOURCES")
        self.rpmbuild_builddir = os.path.join(self.rpmbuild_dir, "BUILD")

        # A copy of the git code from commit we're building:
        self.rpmbuild_gitcopy = os.path.join(self.rpmbuild_sourcedir,
                self.tgz_dir)

        # Set to true if we've already created a tgz:
        self.ran_tgz = False

        # NOTE: These are defined later when/if we actually dump a copy of the
        # project source at the tag we're building. Only then can we search for
        # a spec file.
        self.spec_file_name = None
        self.spec_file = None

        # List of full path to all sources for this package.
        self.sources = []

        # Set to path to srpm once we build one.
        self.srpm_location = None

    def run(self, options):
        """
        Perform the actions requested of the builder.

        NOTE: this method may do nothing if the user requested no build actions
        be performed. (i.e. only release tagging, etc)
        """
        print("Building package [%s]" % (self.build_tag))
        self.no_cleanup = options.no_cleanup

        if options.tgz:
            self.tgz()
        if options.srpm:
            self._srpm()
        if options.rpm:
            self._rpm()

        # Submit builds to brew/koji if requested:
        koji_opts = DEFAULT_KOJI_OPTS
        if options.koji_opts:
            koji_opts = options.koji_opts
        if options.brew:
            self._submit_build("brew", koji_opts, options.brew)
        if options.koji:
            self._submit_build("koji", koji_opts, options.koji)

        self.cleanup()

    def tgz(self):
        """
        Create the .tar.gz required to build this package.

        Returns full path to the created tarball.
        """
        self._setup_sources()

        run_command("cp %s/%s %s/" %  \
                (self.rpmbuild_sourcedir, self.tgz_filename,
                    self.rpmbuild_basedir))

        self.ran_tgz = True
        full_path = os.path.join(self.rpmbuild_basedir, self.tgz_filename)
        print "Wrote: %s" % full_path
        self.sources.append(full_path)
        return full_path

    def _setup_sources(self):
        """
        Create a copy of the git source for the project at the point in time
        our build tag was created.

        Created in the temporary rpmbuild SOURCES directory.
        """
        self._create_build_dirs()

        print("Creating %s from git tag: %s..." % (self.tgz_filename, 
            self.git_commit_id))
        create_tgz(self.git_root, self.tgz_dir, self.git_commit_id, 
                self.relative_project_dir, self.rel_eng_dir, 
                os.path.join(self.rpmbuild_sourcedir, self.tgz_filename))

        # Extract the source so we can get at the spec file, etc.
        debug("Copying git source to: %s" % self.rpmbuild_gitcopy)
        run_command("cd %s/ && tar xzf %s" % (self.rpmbuild_sourcedir,
            self.tgz_filename))

        # NOTE: The spec file we actually use is the one exported by git
        # archive into the temp build directory. This is done so we can
        # modify the version/release on the fly when building test rpms
        # that use a git SHA1 for their version.
        self.spec_file_name = find_spec_file(in_dir=self.rpmbuild_gitcopy)
        self.spec_file = os.path.join(self.rpmbuild_gitcopy, self.spec_file_name)

    def _srpm(self):
        """
        Build a source RPM.
        """
        self._create_build_dirs()
        if not self.ran_tgz:
            self.tgz()

        if self.test:
            self._setup_test_specfile()

        debug("Creating srpm from spec file: %s" % self.spec_file)
        define_dist = ""
        if self.dist:
            define_dist = "--define 'dist %s'" % self.dist

        cmd = "rpmbuild %s %s --nodeps -bs %s" % \
                (self._get_rpmbuild_dir_options(), define_dist, self.spec_file)
        output = run_command(cmd)
        print(output)
        self.srpm_location = self._find_wrote_in_rpmbuild_output(output)[0]

    def _rpm(self):
        """ Build an RPM. """
        self._create_build_dirs()
        if not self.ran_tgz:
            self.tgz()

        if self.test:
            self._setup_test_specfile()

        define_dist = ""
        if self.dist:
            define_dist = "--define 'dist %s'" % self.dist
        cmd = "rpmbuild %s %s --nodeps --clean -ba %s" % \
                (self._get_rpmbuild_dir_options(), define_dist, self.spec_file)
        output = run_command(cmd)
        print output
        files_written = self._find_wrote_in_rpmbuild_output(output)
        if len(files_written) < 2:
            error_out("Error parsing rpmbuild output")
        self.srpm_location = files_written[0]

    def _submit_build(self, executable, koji_opts, tag):
        """ Submit srpm to brew/koji. """
        cmd = "%s %s %s %s" % (executable, koji_opts, tag, self.srpm_location)
        print("\nSubmitting build with: %s" % cmd)
        output = run_command(cmd)
        print(output)

    def _find_wrote_in_rpmbuild_output(self, output):
        """
        Parse the output from rpmbuild looking for lines beginning with
        "Wrote:". Return a list of file names for each path found.
        """
        paths = []
        look_for = "Wrote: "
        for line in output.split("\n"):
            if line.startswith(look_for):
                paths.append(line[len(look_for):])
                debug("Found wrote line: %s" % paths[-1])
        if (len(paths) == 0):
            error_out("Unable to locate 'Wrote: ' lines in rpmbuild output")
        return paths

    def cleanup(self, force=False):
        """
        Remove all temporary files and directories.
        """
        if force or not self.no_cleanup:
            commands.getoutput("rm -rf %s" % self.rpmbuild_dir)

    def _create_build_dirs(self):
        """
        Create the build directories. Can safely be called multiple times.
        """
        commands.getoutput("mkdir -p %s %s %s %s" % (self.rpmbuild_basedir,
            self.rpmbuild_dir, self.rpmbuild_sourcedir, self.rpmbuild_builddir))

    def _setup_test_specfile(self):
        if self.test:
            # If making a test rpm we need to get a little crazy with the spec
            # file we're building off. (note that this is a temp copy of the
            # spec) Swap out the actual release for one that includes the git
            # SHA1 we're building for our test package:
            cmd = "perl %s/test-setup-specfile.pl %s %s %s-%s %s" % \
                    (
                        self.rel_eng_dir,
                        self.spec_file,
                        self.git_commit_id,
                        self.project_name,
                        self.display_version,
                        self.tgz_filename
                    )
            run_command(cmd)

    def _get_rpmbuild_dir_options(self):
        return """--define "_sourcedir %s" --define "_builddir %s" --define "_srcrpmdir %s" --define "_rpmdir %s" """ % \
            (self.rpmbuild_sourcedir, self.rpmbuild_builddir,
                    self.rpmbuild_basedir, self.rpmbuild_basedir)

    def _get_tgz_name_and_ver(self):
        """
        Returns the project name for the .tar.gz to build. Normally this is
        just the project name, but in the case of Satellite packages it may
        be different.
        """
        return "%s-%s" % (self.project_name, self.display_version)

    def _get_display_version(self):
        """
        Get the package display version to build.

        Normally this is whatever is rel-eng/packages/. In the case of a --test
        build it will be the SHA1 for the HEAD commit of the current git
        branch.
        """
        if self.test:
            version = "git-" + get_git_head_commit()
        else:
            version = self.build_version.split("-")[0]
        return version



class NoTgzBuilder(Builder):
    """
    Builder for packages that do not require the creation of a tarball.
    Usually these packages have source tarballs checked directly into git.
    i.e. most of the packages in spec-tree.
    """
    def tgz(self):
        """ Override parent behavior, we already have a tgz. """
        # TODO: Does it make sense to allow user to create a tgz for this type
        # of project?
        self._setup_sources()
        self.ran_tgz = True

        source_suffixes = ('.tar.gz', '.tar', '.zip', '.jar')
        debug("Scanning for sources.")
        for filename in os.listdir(self.rpmbuild_gitcopy):
            for suffix in source_suffixes:
                if filename.endswith(suffix):
                    self.sources.append(os.path.join(self.rpmbuild_gitcopy,
                        filename))
        debug("  Sources: %s" % self.sources)

    def _get_rpmbuild_dir_options(self):
        """
        Override parent behavior slightly.

        These packages store tar's, patches, etc, directly in their project
        dir, use the git copy we create as the sources directory when
        building package so everything can be found:
        """
        return """--define "_sourcedir %s" --define "_builddir %s" --define "_srcrpmdir %s" --define "_rpmdir %s" """ % \
            (self.rpmbuild_gitcopy, self.rpmbuild_builddir,
                    self.rpmbuild_basedir, self.rpmbuild_basedir)

    def _setup_test_specfile(self):
        """ Override parent behavior. """
        if self.test:
            # If making a test rpm we need to get a little crazy with the spec
            # file we're building off. (note that this is a temp copy of the
            # spec) Swap out the actual release for one that includes the git
            # SHA1 we're building for our test package:
            cmd = "perl %s/test-setup-specfile.pl %s %s" % \
                    (
                        self.rel_eng_dir,
                        self.spec_file,
                        self.git_commit_id
                    )
            run_command(cmd)



class DummyBuilder(NoTgzBuilder):
    """ 
    Dummy Builder

    Does nothing if requested to build a tar.gz, but will error
    out if requested to make an srpm or rpm.
    """
    def _srpm(self):
        error_out("Cannot build source rpm for this project.")

    def _rpm(self):
        error_out("Cannot build rpm for this project.")



class SatelliteBuilder(NoTgzBuilder):
    """
    Builder for packages that are based off some upstream version in Spacewalk
    git. Commits applied in Satellite git become patches applied to the 
    upstream Spacewalk tarball.

    i.e. satellite-java-0.4.0-5 built from spacewalk-java-0.4.0-1 and any 
    patches applied in satellite git.
    i.e. spacewalk-setup-0.4.0-20 built from spacewalk-setup-0.4.0-1 and any
    patches applied in satellite git.
    """
    def __init__(self, name=None, version=None, tag=None, build_dir=None,
            pkg_config=None, global_config=None, dist=None, test=False,
            offline=False):

        NoTgzBuilder.__init__(self, name=name, version=version, tag=tag,
                build_dir=build_dir, pkg_config=pkg_config,
                global_config=global_config, dist=dist, test=test,
                offline=offline)

        if not pkg_config or not pkg_config.has_option("buildconfig",
                "upstream_name"):
            # No upstream_name defined, assume we're keeping the project name:
            self.upstream_name = self.project_name
        else:
            self.upstream_name = pkg_config.get("buildconfig", "upstream_name")
        # Need to assign these after we've exported a copy of the spec file:
        self.upstream_version = None 
        self.upstream_tag = None
        self.patch_filename = None
        self.patch_file = None

    def tgz(self):
        """
        Override parent behavior, we need a tgz from the upstream spacewalk
        project we're based on.
        """
        # TODO: Wasteful step here, all we really need is a way to look for a
        # spec file at the point in time this release was tagged.
        NoTgzBuilder._setup_sources(self)
        # If we knew what it was named at that point in time we could just do:
        # Export a copy of our spec file at the revision to be built:
#        cmd = "git show %s:%s%s > %s" % (self.git_commit_id,
#                self.relative_project_dir, self.spec_file_name,
#                self.spec_file)
#        debug(cmd)
        self._create_build_dirs()

        self.upstream_version = self._get_upstream_version()
        self.upstream_tag = "%s-%s-1" % (self.upstream_name, 
                self.upstream_version)

        print("Building upstream tgz for tag [%s]" % (self.upstream_tag))
        if self.upstream_tag != self.build_tag:
            check_tag_exists(self.upstream_tag, offline=self.offline)

        self.spec_file = os.path.join(self.rpmbuild_sourcedir, 
                self.spec_file_name)
        run_command("cp %s %s" % (os.path.join(self.rpmbuild_gitcopy, 
            self.spec_file_name), self.spec_file))

        # Create the upstream tgz:
        prefix = "%s-%s" % (self.upstream_name, self.upstream_version)
        tgz_filename = "%s.tar.gz" % prefix
        commit = get_build_commit(tag=self.upstream_tag)
        relative_dir = get_relative_project_dir(
                project_name=self.upstream_name, commit=commit)
        tgz_fullpath = os.path.join(self.rpmbuild_sourcedir, tgz_filename)
        print("Creating %s from git tag: %s..." % (tgz_filename, commit))
        create_tgz(self.git_root, prefix, commit, relative_dir, 
                self.rel_eng_dir, tgz_fullpath)
        self.ran_tgz = True

        # If these are equal then the tag we're building was likely created in 
        # Spacewalk and thus we don't need to do any patching.
        if (self.upstream_tag == self.build_tag and not self.test):
            return

        self._generate_patches()
        self._insert_patches_into_spec_file()
        self.sources.append(tgz_fullpath)

    def _generate_patches(self):
        """
        Generate patches for any differences between our tag and the
        upstream tag.
        """
        self.patch_filename = "%s-to-%s-%s.patch" % (self.upstream_tag,
                self.project_name, self.build_version)
        self.patch_file = os.path.join(self.rpmbuild_sourcedir,
                self.patch_filename)
        os.chdir(os.path.join(self.git_root, self.relative_project_dir))
        print("Generating patch [%s]" % self.patch_filename)
        debug("Patch: %s" % self.patch_file)
        patch_command = "git diff --relative %s..%s > %s" % \
                (self.upstream_tag, self.git_commit_id, self.patch_file)
        debug("Generating patch with: %s" % patch_command)
        output = run_command(patch_command)
        print(output)

    def _insert_patches_into_spec_file(self):
        """
        Insert the generated patches into the copy of the spec file we'll be
        building with.
        """
        f = open(self.spec_file, 'r')
        lines = f.readlines()

        patch_pattern = re.compile('^Patch(\d+):')
        source_pattern = re.compile('^Source\d+:')

        # Find the largest PatchX: line, or failing that SourceX:
        patch_number = 0 # What number should we use for our PatchX line
        patch_insert_index = 0 # Where to insert our PatchX line in the list
        patch_apply_index = 0 # Where to insert our %patchX line in the list
        array_index = 0 # Current index in the array
        for line in lines:
            match = source_pattern.match(line)
            if match:
                patch_insert_index = array_index + 1

            match = patch_pattern.match(line)
            if match:
                patch_insert_index = array_index + 1
                patch_number = int(match.group(1)) + 1

            if line.startswith("%setup"):
                patch_apply_index = array_index + 2 # already added a line

            array_index += 1
        
        if patch_insert_index == 0 or patch_apply_index == 0:
            error_out("Unable to insert PatchX or %patchX lines in spec file")

        lines.insert(patch_insert_index, "Patch%s: %s\n" % (patch_number, 
            self.patch_filename))
        lines.insert(patch_apply_index, "%%patch%s -p1 -b .%s\n" % (patch_number,
            self.patch_filename[0:-len(".patch")]))
        f.close()

        # Now write out the modified lines to the spec file copy:
        f = open(self.spec_file, 'w')
        for line in lines:
            f.write(line)
        f.close()

    def _get_upstream_version(self):
        """
        Get the upstream version. Checks for "upstreamversion" in the spec file
        and uses it if found. Otherwise assumes the upstream version is equal 
        to the version we're building.

        i.e. satellite-java-0.4.15 will be built on spacewalk-java-0.4.15
        with just the package release being incremented on rebuilds. 
        """
        # Use upstreamversion if defined in the spec file:
        (status, output) = commands.getstatusoutput(
            "cat %s | grep 'define upstreamversion' | awk '{ print $3 ; exit }'" %
            self.spec_file)
        if status == 0 and output != "":
            return output

        if self.test:
            return self.build_version.split("-")[0]
        # Otherwise, assume we use our version:
        else:
            return self.display_version

    def _get_rpmbuild_dir_options(self):
        """
        Override parent behavior slightly.

        These packages store tar's, patches, etc, directly in their project
        dir, use the git copy we create as the sources directory when
        building package so everything can be found:
        """
        return """--define "_sourcedir %s" --define "_builddir %s" --define "_srcrpmdir %s" --define "_rpmdir %s" """ % \
            (self.rpmbuild_sourcedir, self.rpmbuild_builddir,
                    self.rpmbuild_basedir, self.rpmbuild_basedir)


