"""Matchzoo pair generator."""

from matchzoo import engine
from matchzoo import datapack
from matchzoo import utils
from matchzoo import tasks

import pandas as pd
import numpy as np
import typing


class PairGenerator(engine.BaseGenerator):
    """PairGenerator for Matchzoo.

    Pair generator can be used only for ranking.

    Examples:
        >>> np.random.seed(111)
        >>> relation = [['qid0', 'did0', 0],
        ...             ['qid0', 'did1', 1],
        ...             ['qid0', 'did2', 2]
        ... ]
        >>> left = [['qid0', [1, 2]]]
        >>> right = [['did0', [2, 3]],
        ...          ['did1', [3, 4]],
        ...          ['did2', [4, 5]],
        ... ]
        >>> relation = pd.DataFrame(relation,
        ...                         columns=['id_left', 'id_right', 'label'])
        >>> left = pd.DataFrame(left, columns=['id_left', 'text_left'])
        >>> left.set_index('id_left', inplace=True)
        >>> right = pd.DataFrame(right, columns=['id_right', 'text_right'])
        >>> right.set_index('id_right', inplace=True)
        >>> input = datapack.DataPack(relation=relation,
        ...                           left=left,
        ...                           right=right
        ... )
        >>> generator = PairGenerator(input, 1, 1, 1, 'train', True)
        >>> len(generator)
        2
        >>> x, y = generator[0]
        >>> x['text_left'].tolist()
        [[1, 2], [1, 2]]
        >>> x['text_right'].tolist()
        [[3, 4], [2, 3]]
        >>> x['id_left'].tolist()
        ['qid0', 'qid0']
        >>> x['id_right'].tolist()
        ['did1', 'did0']
        >>> y.tolist()
        [1.0, 0.0]

    """

    def __init__(
        self,
        inputs: datapack.DataPack,
        num_neg: int = 1,
        num_dup: int = 4,
        batch_size: int = 32,
        stage: str = 'train',
        shuffle: bool = True
    ):
        """Construct the pair generator.

        :param inputs: the output generated by :class:`DataPack`.
        :param num_neg: the number of negative samples associated with each
            positive sample.
        :param num_dup: the number of duplicates for each positive sample.
        This variable is used to balance samples since there are always many
        more negative sample than positive sample, thus, we use num_dup to
        duplicate those positive samples.
        :param batch_size: number of instances in a batch.
        :param stage: String indicate the pre-processing stage, `train`,
            `evaluate`, or `predict` expected.
        :param shuffle: whether to shuffle the instances while generating a
            batch.
        """
        self._num_neg = num_neg
        self._num_dup = num_dup
        self._left = inputs.left
        self._right = inputs.right
        self._task = tasks.Ranking()
        self._relation = self.transform_relation(inputs.relation)
        num_pairs = len(self._relation) // (self._num_neg + 1)
        super().__init__(batch_size, num_pairs, stage, shuffle)

    def transform_relation(self, relations: pd.DataFrame) -> pd.DataFrame:
        """Obtain the transformed data from :class:`DataPack`.

        Note here, label is required to make pairs.

        TODO: support dynamic size of pairs while number of negative samples is
        less than `_num_neg`.

        :param relations: An instance of :class:`DataPack` to be transformed.
        :return: the output of all the transformed relations.
        """
        if 'label' not in relations.columns:
            raise ValueError(f"label is required from {relations} \
                             to generate pairs.")
        relations['label'] = relations['label'].astype(
            self._task.output_dtype)
        # Note here the main id is set to be the id_left
        pairs = []
        groups = relations.sort_values('label',
                                       ascending=False).groupby('id_left')
        for idx, group in groups:
            labels = group.label.unique()
            for label in labels:
                pos_samples = group[group.label == label]
                pos_samples = pd.concat([pos_samples] * self._num_dup)
                neg_samples = group[group.label < label]
                for _, pos_sample in pos_samples.iterrows():
                    pos_sample = pd.DataFrame([pos_sample])
                    if len(neg_samples) >= self._num_neg:
                        neg_sample = neg_samples.sample(self._num_neg,
                                                        replace=False)
                        pairs.extend((pos_sample, neg_sample))
        return pd.concat(pairs, ignore_index=True)

    def _get_batch_of_transformed_samples(
        self,
        index_array: np.array
    ) -> typing.Tuple[dict, typing.Any]:
        """Get a batch of samples based on their ids.

        :param index_array: a list of instance ids.
        :return: A batch of transformed samples.
        """
        trans_index = []
        steps = self._num_neg + 1
        for item in index_array:
            trans_index.extend(list(range(item * steps, (item + 1) * steps)))
        batch_x = {}
        batch_y = self._relation.iloc[trans_index, 2].values

        left_column = self._left.columns.values.tolist()
        right_column = self._right.columns.values.tolist()
        columns = left_column + right_column + ['id_left', 'id_right']
        for column in columns:
            batch_x[column] = []

        id_left = self._relation.iloc[trans_index, 0]
        id_right = self._relation.iloc[trans_index, 1]

        batch_x['id_left'] = id_left
        batch_x['id_right'] = id_right

        for column in self._left.columns:
            batch_x[column] = self._left.loc[id_left, column].tolist()
        for column in self._right.columns:
            batch_x[column] = self._right.loc[id_right, column].tolist()

        for key, val in batch_x.items():
            batch_x[key] = np.array(val)

        batch_x = utils.dotdict(batch_x)
        return batch_x, batch_y
