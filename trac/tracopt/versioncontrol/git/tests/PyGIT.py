# -*- coding: utf-8 -*-
#
# Copyright (C) 2012-2023 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import os
import subprocess
import tempfile
import unittest
from datetime import datetime

from trac.test import EnvironmentStub, makeSuite, mkdtemp, rmtree
from trac.util import create_file
from trac.versioncontrol.api import Changeset, DbRepositoryProvider, \
                                    RepositoryManager
from tracopt.versioncontrol.git.PyGIT import GitCore, GitError, Storage, \
                                             SizedDict, StorageFactory, \
                                             parse_commit
from tracopt.versioncontrol.git.tests.git_fs import GitCommandMixin


class GitTestCase(unittest.TestCase):

    def test_is_sha(self):
        self.assertFalse(GitCore.is_sha(b'123'))
        self.assertTrue(GitCore.is_sha(b'1a3f'))
        self.assertTrue(GitCore.is_sha(b'f' * 40))
        self.assertFalse(GitCore.is_sha(b'x' + b'f' * 39))
        self.assertFalse(GitCore.is_sha(b'f' * 41))

    def test_git_version(self):
        v = Storage.git_version()
        self.assertIsInstance(v, dict)
        self.assertTrue(v['v_compatible'])
        self.assertIsInstance(v['v_str'], str)
        self.assertGreaterEqual(len(v['v_tuple']), 3)
        self.assertIsInstance(v['v_tuple'][0], int)
        self.assertIsInstance(v['v_tuple'][1], int)
        self.assertIsInstance(v['v_tuple'][2], int)


class TestParseCommit(unittest.TestCase):
    # The ''' ''' lines are intended to keep lines with trailing whitespace
    commit2240a7b = '''\
tree b19535236cfb6c64b798745dd3917dafc27bcd0a
parent 30aaca4582eac20a52ac7b2ec35bdb908133e5b1
parent 5a0dc7365c240795bf190766eba7a27600be3b3e
author Linus Torvalds <torvalds@linux-foundation.org> 1323915958 -0800
committer Linus Torvalds <torvalds@linux-foundation.org> 1323915958 -0800
mergetag object 5a0dc7365c240795bf190766eba7a27600be3b3e
 type commit
 tag tytso-for-linus-20111214A
 tagger Theodore Ts'o <tytso@mit.edu> 1323890113 -0500
 ''' '''
 tytso-for-linus-20111214
 -----BEGIN PGP SIGNATURE-----
 Version: GnuPG v1.4.10 (GNU/Linux)
 ''' '''
 iQIcBAABCAAGBQJO6PXBAAoJENNvdpvBGATwpuEP/2RCxmdWYZ8/6Z6pmTh3hHN5
 fx6HckTdvLQOvbQs72wzVW0JKyc25QmW2mQc5z3MjSymjf/RbEKihPUITRNbHrTD
 T2sP/lWu09AKLioEg4ucAKn/A7Do3UDIkXTszvVVP/t2psVPzLeJ1njQKra14Nyz
 o0+gSlnwuGx9WaxfR+7MYNs2ikdSkXIeYsiFAOY4YOxwwC99J/lZ0YaNkbI7UBtC
 yu2XLIvPboa5JZXANq2G3VhVIETMmOyRTCC76OAXjqkdp9nLFWDG0ydqQh0vVZwL
 xQGOmAj+l3BNTE0QmMni1w7A0SBU3N6xBA5HN6Y49RlbsMYG27aN54Fy5K2R41I3
 QXVhBL53VD6b0KaITcoz7jIGIy6qk9Wx+2WcCYtQBSIjL2YwlaJq0PL07+vRamex
 sqHGDejcNY87i6AV0DP6SNuCFCi9xFYoAoMi9Wu5E9+T+Vck0okFzW/luk/FvsSP
 YA5Dh+vISyBeCnWQvcnBmsUQyf8d9MaNnejZ48ath+GiiMfY8USAZ29RAG4VuRtS
 9DAyTTIBA73dKpnvEV9u4i8Lwd8hRVMOnPyOO785NwEXk3Ng08pPSSbMklW6UfCY
 4nr5UNB13ZPbXx4uoAvATMpCpYxMaLEdxmeMvgXpkekl0hHBzpVDey1Vu9fb/a5n
 dQpo6WWG9HIJ23hOGAGR
 =n3Lm
 -----END PGP SIGNATURE-----

Merge tag 'tytso-for-linus-20111214' of git://git.kernel.org/pub/scm/linux/kernel/git/tytso/ext4

* tag 'tytso-for-linus-20111214' of git://git.kernel.org/pub/scm/linux/kernel/git/tytso/ext4:
  ext4: handle EOF correctly in ext4_bio_write_page()
  ext4: remove a wrong BUG_ON in ext4_ext_convert_to_initialized
  ext4: correctly handle pages w/o buffers in ext4_discard_partial_buffers()
  ext4: avoid potential hang in mpage_submit_io() when blocksize < pagesize
  ext4: avoid hangs in ext4_da_should_update_i_disksize()
  ext4: display the correct mount option in /proc/mounts for [no]init_itable
  ext4: Fix crash due to getting bogus eh_depth value on big-endian systems
  ext4: fix ext4_end_io_dio() racing against fsync()

.. using the new signed tag merge of git that now verifies the gpg
signature automatically.  Yay.  The branchname was just 'dev', which is
prettier.  I'll tell Ted to use nicer tag names for future cases.
'''

    def test_parse(self):
        msg, props = parse_commit(self.commit2240a7b)
        self.assertTrue(msg)
        self.assertTrue(props)
        self.assertEqual(
            ['30aaca4582eac20a52ac7b2ec35bdb908133e5b1',
             '5a0dc7365c240795bf190766eba7a27600be3b3e'],
            props['parent'])
        self.assertEqual(
            ['Linus Torvalds <torvalds@linux-foundation.org> 1323915958 -0800'],
            props['author'])
        self.assertEqual(props['author'], props['committer'])

        # Merge tag
        self.assertEqual(['''\
object 5a0dc7365c240795bf190766eba7a27600be3b3e
type commit
tag tytso-for-linus-20111214A
tagger Theodore Ts\'o <tytso@mit.edu> 1323890113 -0500

tytso-for-linus-20111214
-----BEGIN PGP SIGNATURE-----
Version: GnuPG v1.4.10 (GNU/Linux)

iQIcBAABCAAGBQJO6PXBAAoJENNvdpvBGATwpuEP/2RCxmdWYZ8/6Z6pmTh3hHN5
fx6HckTdvLQOvbQs72wzVW0JKyc25QmW2mQc5z3MjSymjf/RbEKihPUITRNbHrTD
T2sP/lWu09AKLioEg4ucAKn/A7Do3UDIkXTszvVVP/t2psVPzLeJ1njQKra14Nyz
o0+gSlnwuGx9WaxfR+7MYNs2ikdSkXIeYsiFAOY4YOxwwC99J/lZ0YaNkbI7UBtC
yu2XLIvPboa5JZXANq2G3VhVIETMmOyRTCC76OAXjqkdp9nLFWDG0ydqQh0vVZwL
xQGOmAj+l3BNTE0QmMni1w7A0SBU3N6xBA5HN6Y49RlbsMYG27aN54Fy5K2R41I3
QXVhBL53VD6b0KaITcoz7jIGIy6qk9Wx+2WcCYtQBSIjL2YwlaJq0PL07+vRamex
sqHGDejcNY87i6AV0DP6SNuCFCi9xFYoAoMi9Wu5E9+T+Vck0okFzW/luk/FvsSP
YA5Dh+vISyBeCnWQvcnBmsUQyf8d9MaNnejZ48ath+GiiMfY8USAZ29RAG4VuRtS
9DAyTTIBA73dKpnvEV9u4i8Lwd8hRVMOnPyOO785NwEXk3Ng08pPSSbMklW6UfCY
4nr5UNB13ZPbXx4uoAvATMpCpYxMaLEdxmeMvgXpkekl0hHBzpVDey1Vu9fb/a5n
dQpo6WWG9HIJ23hOGAGR
=n3Lm
-----END PGP SIGNATURE-----'''], props['mergetag'])

        # Message
        self.assertEqual("""Merge tag 'tytso-for-linus-20111214' of git://git.kernel.org/pub/scm/linux/kernel/git/tytso/ext4

* tag 'tytso-for-linus-20111214' of git://git.kernel.org/pub/scm/linux/kernel/git/tytso/ext4:
  ext4: handle EOF correctly in ext4_bio_write_page()
  ext4: remove a wrong BUG_ON in ext4_ext_convert_to_initialized
  ext4: correctly handle pages w/o buffers in ext4_discard_partial_buffers()
  ext4: avoid potential hang in mpage_submit_io() when blocksize < pagesize
  ext4: avoid hangs in ext4_da_should_update_i_disksize()
  ext4: display the correct mount option in /proc/mounts for [no]init_itable
  ext4: Fix crash due to getting bogus eh_depth value on big-endian systems
  ext4: fix ext4_end_io_dio() racing against fsync()

.. using the new signed tag merge of git that now verifies the gpg
signature automatically.  Yay.  The branchname was just 'dev', which is
prettier.  I'll tell Ted to use nicer tag names for future cases.""", msg)


class NormalTestCase(unittest.TestCase, GitCommandMixin):

    def setUp(self):
        self.env = EnvironmentStub()
        self.repos_path = mkdtemp()
        # create git repository and master branch
        self._git('init')
        self._git('config', 'core.quotepath', 'true')  # ticket:11198
        self._git('config', 'user.name', "Joe")
        self._git('config', 'user.email', "joe@example.com")
        create_file(os.path.join(self.repos_path, '.gitignore'))
        self._git('add', '.gitignore')
        self._git_commit('-a', '-m', 'test',
                         date=datetime(2013, 1, 1, 9, 4, 56))

    def tearDown(self):
        RepositoryManager(self.env).reload_repositories()
        StorageFactory._clean()
        self.env.reset_db()
        if os.path.isdir(self.repos_path):
            rmtree(self.repos_path)

    def _factory(self, weak, path=None):
        if path is None:
            path = os.path.join(self.repos_path, '.git')
        return StorageFactory(path, self.env.log, weak)

    def _storage(self, path=None):
        if path is None:
            path = os.path.join(self.repos_path, '.git')
        return Storage(path, self.env.log, self.git_bin, 'utf-8')

    def test_control_files_detection(self):
        # Exception not raised when path points to ctrl file dir
        self.assertIsInstance(self._storage().repo, GitCore)
        # Exception not raised when path points to parent of ctrl files dir
        self.assertIsInstance(self._storage(self.repos_path).repo, GitCore)
        # Exception raised when path points to dir with no ctrl files
        path = tempfile.mkdtemp(dir=self.repos_path)
        self.assertRaises(GitError, self._storage, path)
        # Exception raised if a ctrl file is missing
        os.remove(os.path.join(self.repos_path, '.git', 'HEAD'))
        self.assertRaises(GitError, self._storage, self.repos_path)

    @unittest.skipIf(os.name == 'nt', 'Control characters cannot be used in '
                                      'filesystem on Windows')
    def test_get_branches_with_cr_in_commitlog(self):
        # regression test for #11598
        message = 'message with carriage return'.replace(' ', '\r')

        create_file(os.path.join(self.repos_path, 'ticket11598.txt'))
        self._git('add', 'ticket11598.txt')
        self._git_commit('-m', message,
                         date=datetime(2013, 5, 9, 11, 5, 21))

        storage = self._storage()
        branches = sorted(storage.get_branches())
        self.assertEqual('master', branches[0][0])
        self.assertEqual(1, len(branches))

    def test_rev_is_anchestor_of(self):
        # regression test for #11215
        path = os.path.join(self.repos_path, '.git')
        DbRepositoryProvider(self.env).add_repository('gitrepos', path, 'git')
        repos = RepositoryManager(self.env).get_repository('gitrepos')
        parent_rev = repos.youngest_rev

        create_file(os.path.join(self.repos_path, 'ticket11215.txt'))
        self._git('add', 'ticket11215.txt')
        self._git_commit('-m', 'ticket11215',
                         date=datetime(2013, 6, 27, 18, 26, 2))
        repos.sync()
        rev = repos.youngest_rev

        self.assertEqual(rev, repos.normalize_rev(rev[:7]))
        self.assertNotEqual(rev, parent_rev)
        self.assertFalse(repos.rev_older_than(None, None))
        self.assertFalse(repos.rev_older_than(None, rev[:7]))
        self.assertFalse(repos.rev_older_than(rev[:7], None))
        self.assertTrue(repos.rev_older_than(parent_rev, rev))
        self.assertTrue(repos.rev_older_than(parent_rev[:7], rev[:7]))
        self.assertFalse(repos.rev_older_than(rev, parent_rev))
        self.assertFalse(repos.rev_older_than(rev[:7], parent_rev[:7]))

    def test_node_get_history_with_empty_commit(self):
        # regression test for #11328
        path = os.path.join(self.repos_path, '.git')
        DbRepositoryProvider(self.env).add_repository('gitrepos', path, 'git')
        repos = RepositoryManager(self.env).get_repository('gitrepos')
        parent_rev = repos.youngest_rev

        self._git_commit('-m', 'ticket:11328', '--allow-empty',
                         date=datetime(2013, 10, 15, 9, 46, 27))
        repos.sync()
        rev = repos.youngest_rev

        node = repos.get_node('', rev)
        self.assertEqual(rev, repos.git.last_change(rev, ''))
        history = list(node.get_history())
        self.assertEqual('', history[0][0])
        self.assertEqual(rev, history[0][1])
        self.assertEqual(Changeset.EDIT, history[0][2])
        self.assertEqual('', history[1][0])
        self.assertEqual(parent_rev, history[1][1])
        self.assertEqual(Changeset.ADD, history[1][2])
        self.assertEqual(2, len(history))

    def test_sync_after_removing_branch(self):
        self._git('checkout', '-b', 'b1', 'master')
        self._git('checkout', 'master')
        create_file(os.path.join(self.repos_path, 'newfile.txt'))
        self._git('add', 'newfile.txt')
        self._git_commit('-m', 'added newfile.txt to master',
                         date=datetime(2013, 12, 23, 6, 52, 23))

        storage = self._storage()
        storage.sync()
        self.assertEqual(['b1', 'master'],
                         sorted(b[0] for b in storage.get_branches()))
        self._git('branch', '-D', 'b1')
        self.assertTrue(storage.sync())
        self.assertEqual(['master'],
                         sorted(b[0] for b in storage.get_branches()))
        self.assertFalse(storage.sync())

    def test_turn_off_persistent_cache(self):
        # persistent_cache is enabled
        parent_rev = self._factory(False).getInstance().youngest_rev()

        create_file(os.path.join(self.repos_path, 'newfile.txt'))
        self._git('add', 'newfile.txt')
        self._git_commit('-m', 'test_turn_off_persistent_cache',
                         date=datetime(2014, 1, 29, 13, 13, 25))

        # persistent_cache is disabled
        rev = self._factory(True).getInstance().youngest_rev()
        self.assertNotEqual(rev, parent_rev)

    @unittest.skipIf(os.name == 'nt', 'Control characters cannot be used in '
                                      'filesystem on Windows')
    def test_ls_tree_with_control_chars(self):
        paths = ['normal-path.txt',
                 '\a\b\t\n\v\f\r\x1b"\\.tx\\t']
        for path in paths:
            create_file(os.path.join(self.repos_path, path))
            self._git('add', path)
        self._git_commit('-m', 'ticket:11180 and ticket:11198')

        storage = self._storage()
        rev = storage.head()
        entries = storage.ls_tree(rev, '/')
        self.assertEqual(['\a\b\t\n\v\f\r\x1b"\\.tx\\t',
                          '.gitignore',
                          'normal-path.txt'],
                         [entry[4] for entry in entries])

    @unittest.skipIf(os.name == 'nt', 'Control characters cannot be used in '
                                      'filesystem on Windows')
    def test_get_historian_with_control_chars(self):
        paths = ['normal-path.txt', '\a\b\t\n\v\f\r\x1b"\\.tx\\t']

        for path in paths:
            create_file(os.path.join(self.repos_path, path))
            self._git('add', path)
        self._git_commit('-m', 'ticket:11180 and ticket:11198')

        def validate(path, quotepath):
            self._git('config', 'core.quotepath', quotepath)
            storage = self._storage()
            rev = storage.head()
            with storage.get_historian('HEAD', path) as historian:
                hrev = storage.last_change('HEAD', path, historian)
                self.assertEqual(rev, hrev)

        validate(paths[0], 'true')
        validate(paths[0], 'false')
        validate(paths[1], 'true')
        validate(paths[1], 'false')

    def test_cat_file_with_large_files(self):
        # regression test for #13327
        # Note that you may want to run this with gevent, by installing gevent
        # and adding
        #
        #   from gevent import monkey
        #   monkey.patch_all()
        #
        # at the top of this file.
        path = os.path.join(self.repos_path, '.git')
        DbRepositoryProvider(self.env).add_repository('gitrepos', path, 'git')
        repos = RepositoryManager(self.env).get_repository('gitrepos')

        # 32 MiB of data, significantly more than you would usually get for
        # one call to read(2).
        data = bytes(bytearray(range(256))) * (4 * 1024 * 32)
        create_file(os.path.join(self.repos_path, 'ticket13327.txt'), data,
                    'wb')
        self._git('add', 'ticket13327.txt')
        self._git_commit('-m', 'add ticket13327.txt',
                         date=datetime(2020, 11, 3, 23, 41, 00))

        repos.sync()
        node = repos.get_node('ticket13327.txt')
        content = node.get_content().read()

        self.assertEqual(32 * 1024 * 1024, len(content))
        self.assertEqual(bytes, type(content))
        self.assertEqual(data, content)


class UnicodeNameTestCase(unittest.TestCase, GitCommandMixin):

    def setUp(self):
        self.env = EnvironmentStub()
        self.repos_path = mkdtemp()
        # create git repository and master branch
        self._git('init')
        self._git('config', 'core.quotepath', 'true')  # ticket:11198
        self._git('config', 'user.name', "Joé")  # passing utf-8 bytes
        self._git('config', 'user.email', "joe@example.com")
        create_file(os.path.join(self.repos_path, '.gitignore'))
        self._git('add', '.gitignore')
        self._git_commit('-a', '-m', 'test',
                         date=datetime(2013, 1, 1, 9, 4, 57))

    def tearDown(self):
        self.env.reset_db()
        if os.path.isdir(self.repos_path):
            rmtree(self.repos_path)

    def _storage(self):
        path = os.path.join(self.repos_path, '.git')
        return Storage(path, self.env.log, self.git_bin, 'utf-8')

    def test_unicode_verifyrev(self):
        storage = self._storage()
        self.assertIsNotNone(storage.verifyrev('master'))
        self.assertIsNone(storage.verifyrev('tété'))

    def test_unicode_filename(self):
        create_file(os.path.join(self.repos_path, 'tickét.txt'))
        self._git('add', 'tickét.txt')
        self._git_commit('-m', 'unicode-filename', date='1359912600 +0100')
        storage = self._storage()
        filenames = sorted(fname for mode, type, sha, size, fname
                                 in storage.ls_tree('HEAD'))
        self.assertEqual(str, type(filenames[0]))
        self.assertEqual(str, type(filenames[1]))
        self.assertEqual('.gitignore', filenames[0])
        self.assertEqual('tickét.txt', filenames[1])
        # check commit author, for good measure
        self.assertEqual('Joé <joe@example.com> 1359912600 +0100',
                         storage.read_commit(storage.head())[1]['author'][0])

    def test_unicode_branches(self):
        self._git('checkout', '-b', 'tickɇt10980', 'master')
        storage = self._storage()
        branches = sorted(storage.get_branches())
        self.assertEqual(str, type(branches[0][0]))
        self.assertEqual(str, type(branches[1][0]))
        self.assertEqual('master', branches[0][0])
        self.assertEqual('tickɇt10980', branches[1][0])

        contains = sorted(storage.get_branch_contains(branches[1][1],
                                                      resolve=True))
        self.assertEqual(str, type(contains[0][0]))
        self.assertEqual(str, type(contains[1][0]))
        self.assertEqual('master', contains[0][0])
        self.assertEqual('tickɇt10980', contains[1][0])

    def test_unicode_tags(self):
        self._git('tag', 'tɐg-t10980', 'master')
        self._git_commit('-m', 'blah', '--allow-empty')
        self._git('tag', 'v0.42.1', 'master')
        storage = self._storage()

        tags = storage.get_tags()
        self.assertEqual(str, type(tags[0]))
        self.assertEqual(['tɐg-t10980', 'v0.42.1'], tags)

        rev = storage.verifyrev('tɐg-t10980')
        self.assertIsNotNone(rev)
        self.assertEqual(['tɐg-t10980'], storage.get_tags(rev))

        rev = storage.verifyrev('v0.42.1')
        self.assertIsNotNone(rev)
        self.assertEqual(['v0.42.1'], storage.get_tags(rev))

    def test_ls_tree_with_unicode_chars(self):
        paths = ['normal-path.txt', 'ŧïckét.txt']
        for path in paths:
            create_file(os.path.join(self.repos_path, path))
            self._git('add', path)
        self._git_commit('-m', 'ticket:11180 and ticket:11198')

        storage = self._storage()
        rev = storage.head()
        entries = storage.ls_tree(rev, '/')
        self.assertEqual(['.gitignore', 'normal-path.txt', 'ŧïckét.txt'],
                         [entry[4] for entry in entries])

    def test_get_historian_with_unicode_chars(self):
        paths = ['normal-path.txt', 'ŧïckét.txt']
        for path in paths:
            create_file(os.path.join(self.repos_path, path))
            self._git('add', path)
        self._git_commit('-m', 'ticket:11180 and ticket:11198')

        def validate(path, quotepath):
            self._git('config', 'core.quotepath', quotepath)
            storage = self._storage()
            rev = storage.head()
            with storage.get_historian('HEAD', path) as historian:
                hrev = storage.last_change('HEAD', path, historian)
                self.assertEqual(rev, hrev)

        validate(paths[0], 'true')
        validate(paths[0], 'false')
        validate(paths[1], 'true')
        validate(paths[1], 'false')


class StorageTestCase(unittest.TestCase, GitCommandMixin):

    def setUp(self):
        self.env = EnvironmentStub()
        self.repos_path = mkdtemp()
        self._git('init', '--bare')

    def tearDown(self):
        self.env.reset_db()
        if os.path.isdir(self.repos_path):
            rmtree(self.repos_path)

    def _storage(self):
        return Storage(self.repos_path, self.env.log, self.git_bin, 'utf-8')

    def _test_srev_dict(self, n_revs, type_):
        with self._spawn_git('fast-import', stdin=subprocess.PIPE) as proc:
            write = proc.stdin.write
            write(b'blob\n')
            write(b'mark :1\n')
            write(b'data 0\n')
            write(b'\n')
            write(b'reset refs/heads/master\n')
            for i in range(n_revs):
                ts = 1000000000 + i
                write(b'commit refs/heads/master\n')
                write(b'mark :2\n')
                write(b'author Joe <joe@example.com> %d +0000\n' % ts)
                write(b'committer Joe <joe@example.com> %d +0000\n' % ts)
                write(b'data 2\n')
                write(b'.\n')
                write(b'M 100644 :1 .gitignore\n')
                write(b'\n')
            stdout, stderr = proc.communicate()
        self.assertEqual(0, proc.returncode,
                         'git exits with %r, stdout %r, stderr %r' %
                         (proc.returncode, stdout, stderr))

        storage = self._storage()
        self.assertIsInstance(storage.rev_cache.srev_dict, type_)
        for i in range(0x10000):
            srev_b = b'%04x' % i
            frev_b = storage.fullrev(srev_b)
            if frev_b is None:
                continue
            self.assertEqual(frev_b[:4], srev_b)
            frev_u = frev_b.decode('ascii')
            srev_u = storage.shortrev(frev_u)
            self.assertTrue(frev_u.startswith(srev_u),
                            'frev_u %(frev_u)r, srev_u %(srev_u)r' % locals())

    def test_srev_dict_a_dict(self):
        self._test_srev_dict(4500, dict)

    def test_srev_dict_a_list(self):
        self._test_srev_dict(5500, list)


class SizedDictTestCase(unittest.TestCase):

    def test_setdefault_raises(self):
        """`setdefault` raises NotImplementedError."""
        self.assertRaises(NotImplementedError, SizedDict().setdefault)


#class GitPerformanceTestCase(unittest.TestCase):
#    """Performance test. Not really a unit test.
#    Not self-contained: Needs a git repository and prints performance result
#    instead of testing anything.
#    TODO: Move to a profiling script?"""
#
#    def test_performance(self):
#        import logging
#        import timeit
#
#        g = Storage(path_to_repo, logging) # Need a git repository path here
#        revs = list(g.get_commits())
#
#        def shortrev_test():
#            for i in revs:
#                i = str(i)
#                s = g.shortrev(i, min_len=4)
#                self.assertTrue(i.startswith(s))
#                self.assertEqual(g.fullrev(s), i)
#
#        iters = 1
#        t = timeit.Timer("shortrev_test()",
#                         "from __main__ import shortrev_test")
#        usec_per_rev = (1000000 * t.timeit(number=iters)/len(revs))
#        print("%.2f usec/rev" % usec_per_rev) # Print instead of testing

#class GitMemoryUsageTestCase(unittest.TestCase):
#    """Memory test. Not really a unit test.
#    Not self-contained: Needs a git repository and prints memory usage
#    instead of testing anything.
#    TODO: Move to a profiling script?"""
#
#    def test_memory_usage(self):
#        import logging
#        import sys
#
#        # custom linux hack reading `/proc/<PID>/statm`
#        if sys.platform == 'linux2':
#            __pagesize = os.sysconf('SC_PAGESIZE')
#
#            def proc_statm(pid = os.getpid()):
#                __proc_statm = '/proc/%d/statm' % pid
#                try:
#                    t = open(__proc_statm)
#                    result = t.read().split()
#                    t.close()
#                    self.assertEqual(7, len(result))
#                    return tuple([ __pagesize*int(p) for p in result ])
#                except:
#                    raise RuntimeError("failed to get memory stats")
#
#        else: # not linux2
#            print("WARNING - meminfo.proc_statm() not available")
#            def proc_statm():
#                return (0,)*7
#
#        print("statm =", proc_statm())
#        __data_size = proc_statm()[5]
#        __data_size_last = [__data_size]
#
#        def print_data_usage():
#            __tmp = proc_statm()[5]
#            print("DATA: %6d %+6d" % (__tmp - __data_size,
#                                      __tmp - __data_size_last[0]))
#            __data_size_last[0] = __tmp
#
#        print_data_usage()
#
#        g = Storage(path_to_repo, logging) # Need a git repository path here
#
#        print_data_usage()
#
#        print("[%s]" % g.head())
#        print(g.ls_tree(g.head()))
#        print("--------------")
#        print_data_usage()
#        print(g.read_commit(g.head()))
#        print("--------------")
#        print_data_usage()
#        p = g.parents(g.head())
#        print(list(p))
#        print("--------------")
#        print(list(g.children(list(p)[0])))
#        print(list(g.children(list(p)[0])))
#        print("--------------")
#        print(g.get_commit_encoding())
#        print("--------------")
#        print(g.get_branches())
#        print("--------------")
#        print(g.hist_prev_revision(g.oldest_rev()), g.oldest_rev(),
#                                   g.hist_next_revision(g.oldest_rev()))
#        print_data_usage()
#        print("--------------")
#        p = g.youngest_rev()
#        print(g.hist_prev_revision(p), p, g.hist_next_revision(p))
#        print("--------------")
#
#        p = g.head()
#        for i in range(-5, 5):
#            print(i, g.history_relative_rev(p, i))
#
#        # check for loops
#        def check4loops(head):
#            print("check4loops", head)
#            seen = {head}
#            for _sha in g.children_recursive(head):
#                if _sha in seen:
#                    print("dupe detected :-/", _sha, len(seen))
#                seen.add(_sha)
#            return seen
#
#        print(len(check4loops(g.parents(g.head())[0])))
#
#        #p = g.head()
#        #revs = [g.history_relative_rev(p, i) for i in range(10)]
#        print_data_usage()
#        revs = list(g.get_commits())
#        print_data_usage()
#
#        #print(len(check4loops(g.oldest_rev())))
#        #print(len(list(g.children_recursive(g.oldest_rev()))))
#
#        print_data_usage()
#
#        # perform typical trac operations:
#
#        if 1:
#            print("--------------")
#            rev = g.head()
#            for mode, _type, sha, _size, name in g.ls_tree(rev):
#                [last_rev] = g.history(rev, name, limit=1)
#                s = g.get_obj_size(sha) if _type == 'blob' else 0
#                msg = g.read_commit(last_rev)
#
#                print("%s %s %10d [%s]" % (_type, last_rev, s, name))
#
#        print("allocating 2nd instance")
#        print_data_usage()
#        g2 = Storage(path_to_repo, logging) # Need a git repository path here
#        g2.head()
#        print_data_usage()
#
#        print("allocating 3rd instance")
#        g3 = Storage(path_to_repo, logging) # Need a git repository path here
#        g3.head()
#        print_data_usage()


def test_suite():
    suite = unittest.TestSuite()
    if GitCommandMixin.git_bin:
        suite.addTest(makeSuite(GitTestCase))
        suite.addTest(makeSuite(TestParseCommit))
        suite.addTest(makeSuite(NormalTestCase))
        suite.addTest(makeSuite(UnicodeNameTestCase))
        suite.addTest(makeSuite(StorageTestCase))
    else:
        print("SKIP: tracopt/versioncontrol/git/tests/PyGIT.py (git cli "
              "binary, 'git', not found)")
    suite.addTest(makeSuite(SizedDictTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
