# Copyright (C) 2015-2018 Camille Scott
# All rights reserved.
#
# This software may be modified and distributed under the terms
# of the BSD license.  See the LICENSE file for details.

from doit.action import CmdAction
from doit.task import clean_targets
import os
import pandas as pd
from sys import stderr

from dammit.tasks.utils import DependentTask, InstallationError
from dammit.profile import profile_task
from dammit.parallel import parallel_fasta
from dammit.fileio.hmmer import HMMerParser
from dammit.fileio.gff3 import GFF3Parser 
from dammit.utils import doit_task, which


class HMMScanTask(DependentTask):

    def deps(self):
        hmmscan = which('hmmscan')
        if hmmscan is None:
            raise InstallationError('hmmscan not found.')
        if self.logger:
            self.logger.debug('hmmscan:' + hmmscan)
        return hmmscan

    @doit_task
    @profile_task
    def task(self, input_filename, output_filename, db_filename,
                   cutoff=0.00001, n_threads=1, sshloginfile=None, 
                   params=None):
        '''Run HMMER's hmmscan with the given database on the given FASTA file.

        Args:
            input_filename (str): The path to the input FASTA.
            output_filename (str): Path to save the results.
            db_filename (str): Path to the formatted database.
            cutoff (float): The e-value cutoff to filter with.
            n_threads (int): Number of threads to use.
            pbs (bool): If True, pass the right parameters to gnu-parallel
                to run on a cluster.
            params (list): Extra parameters to pass to executable.

        Returns:
            dict: A doit task.
        '''

        name = 'hmmscan:' + os.path.basename(input_filename) + '.x.' + \
                        os.path.basename(db_filename)
        stat = output_filename + '.hmmscan.out'
        
        hmmscan_exc = self.deps()
        cmd = [hmmscan_exc]
        if params is not None:
            cmd.extend([str(p) for p in params])
        cmd.extend(['--cpu', '1', '--domtblout', '/dev/stdout', 
                    '-E', str(cutoff), '-o', stat, db_filename, '/dev/stdin'])
        
        cmd = parallel_fasta(input_filename, output_filename, cmd, n_threads, 
                             sshloginfile=sshloginfile)
            
        return {'name': name,
                'actions': [cmd],
                'file_dep': [input_filename, db_filename, db_filename+'.h3p'],
                'targets': [output_filename, stat],
                'clean': [clean_targets]}


class HMMPressTask(DependentTask):

    def deps(self):
        hmmpress = which('hmmpress')
        if hmmpress is None:
            raise InstallationError('hmmpress not found.')
        if self.logger is not None:
            self.logger.debug('hmmpress:' + hmmpress)
        return hmmpress

    @doit_task
    @profile_task
    def task(self, db_filename, params=None, task_dep=None):
        '''Run hmmpress on a profile HMM database.

        Args:
            db_filename (str): The database to run on.
            params (list): Extra parameters to pass to executable.
            task_dep (str): Task dep to add to doit task.

        Returns:
            dict: A doit task.
        '''

        name = 'hmmpress:' + os.path.basename(db_filename)
        exc = self.deps()

        cmd = [exc]
        if params is not None:
            cmd.extend([str(p) for p in params])
        cmd.append(db_filename)

        cmd = ' '.join(cmd)

        task_d =  {'name': name,
                   'actions': [cmd],
                   'targets': [db_filename + ext for ext in ['.h3f', '.h3i', '.h3m', '.h3p']],
                   'uptodate': [True],
                   'clean': [clean_targets]}

        if task_dep is not None:
            task_d['task_dep'] = task_dep

        return task_d


@doit_task
def get_remap_hmmer_task(hmmer_filename, remap_gff_filename, output_filename,
                         transcript_basename='Transcript'):
    '''Given an hmmscan result from the ORFs generated by
    `TransDecoder.LongOrfs` and TransDecoder's GFF3, remap the HMMER results
    so that they refer to the original nucleotide coordinates rather than the
    translated ORF coordinates. Produces a CSV file with columns matching
    those in HMMerParser.

    Args:
        hmmer_filename (str): Path to the `hmmscan` results.
        remap_gff_filename (str): The GFF3 produced by `TransDecoder.LongOrfs`.
        output_filename (str): Path to store remapped results.

    Returns:
        dict: A doit task.
    '''

    name = 'remap_hmmer:{0}'.format(os.path.basename(hmmer_filename))

    def cmd():
        gff_df = GFF3Parser(remap_gff_filename).read()
        hmmer_df = HMMerParser(hmmer_filename,
                               query_basename=transcript_basename).read()

        if len(gff_df) > 0 and len(hmmer_df) > 0:
            merged_df = pd.merge(hmmer_df, gff_df, left_on='full_query_name', right_on='ID')

            hmmer_df['env_coord_from'] = (merged_df.start + \
                                          (3 * merged_df.env_coord_from)).astype(int)
            hmmer_df['env_coord_to'] = (merged_df.start + \
                                        (3 * merged_df.env_coord_to)).astype(int)
            hmmer_df['ali_coord_from'] = (merged_df.start + \
                                          (3 * merged_df.ali_coord_from)).astype(int)
            hmmer_df['ali_coord_to'] = (merged_df.start + \
                                        (3 * merged_df.ali_coord_to)).astype(int)
        
        hmmer_df.to_csv(output_filename, header=True, index=False)

    return {'name': name,
            'actions': [cmd],
            'file_dep': [hmmer_filename, remap_gff_filename],
            'targets': [output_filename],
            'clean': [clean_targets]}

