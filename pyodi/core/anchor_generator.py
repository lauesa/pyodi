import numpy as np
from numpy import ndarray
from typing import List, Optional, Tuple


class AnchorGenerator(object):
    """Standard anchor generator for 2D anchor-based detectors

    Args:
        strides (list[int]): Strides of anchors in multiple feture levels.
        ratios (list[float]): The list of ratios between the height and width
            of anchors in a single level.
        scales (list[int] | None): Anchor scales for anchors in a single level.
            It cannot be set at the same time if `octave_base_scale` and
            `scales_per_octave` are set.
        base_sizes (list[int] | None): The basic sizes of anchors in multiple
            levels. If None is given, strides will be used as base_sizes.
        scale_major (bool): Whether to multiply scales first when generating
            base anchors. If true, the anchors in the same row will have the
            same scales. By default it is True in V2.0
        octave_base_scale (int): The base scale of octave.
        scales_per_octave (int): Number of scales for each octave.
            `octave_base_scale` and `scales_per_octave` are usually used in
            retinanet and the `scales` should be None when they are set.
        centers (list[tuple[float, float]] | None): The centers of the anchor
            relative to the feature grid center in multiple feature levels.
            By default it is set to be None and not used. If a list of tuple of
            float is given, they will be used to shift the centers of anchors.
        center_offset (float): The offset of center in propotion to anchors'
            width and height. By default it is 0 in V2.0.

    Examples:
        >>> from mmdet.core import AnchorGenerator
        >>> self = AnchorGenerator([16], [1.], [1.], [9])
        >>> all_anchors = self.grid_anchors([(2, 2)], device='cpu')
        >>> print(all_anchors)
        [tensor([[-4.5000, -4.5000,  4.5000,  4.5000],
                [11.5000, -4.5000, 20.5000,  4.5000],
                [-4.5000, 11.5000,  4.5000, 20.5000],
                [11.5000, 11.5000, 20.5000, 20.5000]])]
        >>> self = AnchorGenerator([16, 32], [1.], [1.], [9, 18])
        >>> all_anchors = self.grid_anchors([(2, 2), (1, 1)], device='cpu')
        >>> print(all_anchors)
        [tensor([[-4.5000, -4.5000,  4.5000,  4.5000],
                [11.5000, -4.5000, 20.5000,  4.5000],
                [-4.5000, 11.5000,  4.5000, 20.5000],
                [11.5000, 11.5000, 20.5000, 20.5000]]), \
        tensor([[-9., -9., 9., 9.]])]
    """

    def __init__(
        self,
        strides: List[int],
        ratios: List[float],
        scales: Optional[List[float]] = None,
        base_sizes: Optional[List[int]] = None,
        scale_major: bool = True,
        octave_base_scale: None = None,
        scales_per_octave: None = None,
        centers: None = None,
        center_offset: float = 0.0,
    ) -> None:
        # check center and center_offset
        if center_offset != 0:
            assert centers is None, (
                "center cannot be set when center_offset"
                "!=0, {} is given.".format(centers)
            )
        if not (0 <= center_offset <= 1):
            raise ValueError(
                "center_offset should be in range [0, 1], {} is"
                " given.".format(center_offset)
            )
        if centers is not None:
            assert len(centers) == len(strides), (
                "The number of strides should be the same as centers, got "
                "{} and {}".format(strides, centers)
            )

        # calculate base sizes of anchors
        self.strides = strides
        self.base_sizes = list(strides) if base_sizes is None else base_sizes
        assert len(self.base_sizes) == len(self.strides), (
            "The number of strides should be the same as base sizes, got "
            "{} and {}".format(self.strides, self.base_sizes)
        )

        # calculate scales of anchors
        assert (octave_base_scale is not None and scales_per_octave is not None) ^ (
            scales is not None
        ), (
            "scales and octave_base_scale with scales_per_octave cannot"
            " be set at the same time"
        )
        if scales is not None:
            self.scales = np.array(scales)
        elif octave_base_scale is not None and scales_per_octave is not None:
            octave_scales = np.array(
                [2 ** (i / scales_per_octave) for i in range(scales_per_octave)]
            )
            scales = octave_scales * octave_base_scale
            self.scales = np.array(scales)
        else:
            raise ValueError(
                "Either scales or octave_base_scale with "
                "scales_per_octave should be set"
            )

        self.octave_base_scale = octave_base_scale
        self.scales_per_octave = scales_per_octave
        self.ratios = np.array(ratios)
        self.scale_major = scale_major
        self.centers = centers
        self.center_offset = center_offset
        self.base_anchors = self.gen_base_anchors()

    @property
    def num_base_anchors(self):
        return [base_anchors.size(0) for base_anchors in self.base_anchors]

    @property
    def num_levels(self) -> int:
        return len(self.strides)

    def gen_base_anchors(self) -> List[ndarray]:
        multi_level_base_anchors = []
        for i, base_size in enumerate(self.base_sizes):
            center = None
            if self.centers is not None:
                center = self.centers[i]
            multi_level_base_anchors.append(
                self.gen_single_level_base_anchors(
                    base_size, scales=self.scales, ratios=self.ratios, center=center
                )
            )
        return multi_level_base_anchors

    def gen_single_level_base_anchors(
        self, base_size: int, scales: ndarray, ratios: ndarray, center: None = None
    ) -> ndarray:
        w = base_size
        h = base_size
        if center is None:
            x_center = self.center_offset * w
            y_center = self.center_offset * h
        else:
            x_center, y_center = center

        h_ratios = np.sqrt(ratios)
        w_ratios = 1 / h_ratios
        if self.scale_major:
            ws = (w * w_ratios[:, None] * scales[None, :]).flatten()
            hs = (h * h_ratios[:, None] * scales[None, :]).flatten()
        else:
            ws = (w * scales[:, None] * w_ratios[None, :]).flatten()
            hs = (h * scales[:, None] * h_ratios[None, :]).flatten()

        # use float anchor and the anchor's center is aligned with the
        # pixel center
        base_anchors = [
            x_center - 0.5 * ws,
            y_center - 0.5 * hs,
            x_center + 0.5 * ws,
            y_center + 0.5 * hs,
        ]
        base_anchors = np.stack(base_anchors, axis=-1)

        return base_anchors

    def _meshgrid(
        self, x: ndarray, y: ndarray, row_major: bool = True
    ) -> Tuple[ndarray, ndarray]:
        xx = np.tile(x, len(y))
        # yy = y.view(-1, 1).repeat(1, len(x)).view(-1)
        yy = np.tile(np.reshape(y, [-1, 1]), (1, len(x))).flatten()
        if row_major:
            return xx, yy
        else:
            return yy, xx

    def grid_anchors(self, featmap_sizes: List[Tuple[int, int]]) -> List[ndarray]:
        """Generate grid anchors in multiple feature levels

        Args:
            featmap_sizes (list[tuple]): List of feature map sizes in
                multiple feature levels.
            device (str): Device where the anchors will be put on.

        Return:
            list[torch.Tensor]: Anchors in multiple feature levels.
                The sizes of each tensor should be [N, 4], where
                N = width * height * num_base_anchors, width and height
                are the sizes of the corresponding feature lavel,
                num_base_anchors is the number of anchors for that level.
        """
        assert self.num_levels == len(featmap_sizes)
        multi_level_anchors = []
        for i in range(self.num_levels):
            anchors = self.single_level_grid_anchors(
                self.base_anchors[i], featmap_sizes[i], self.strides[i],
            )
            multi_level_anchors.append(anchors)
        return multi_level_anchors

    def single_level_grid_anchors(
        self, base_anchors: ndarray, featmap_size: Tuple[int, int], stride: int = 16
    ) -> ndarray:
        feat_h, feat_w = featmap_size
        shift_x = np.arange(0, feat_w) * stride
        shift_y = np.arange(0, feat_h) * stride
        shift_xx, shift_yy = self._meshgrid(shift_x, shift_y)
        shifts = np.stack([shift_xx, shift_yy, shift_xx, shift_yy], axis=-1)
        shifts = shifts.astype(base_anchors.dtype)
        # first feat_w elements correspond to the first row of shifts
        # add A anchors (1, A, 4) to K shifts (K, 1, 4) to get
        # shifted anchors (K, A, 4), reshape to (K*A, 4)

        all_anchors = base_anchors[None, :, :] + shifts[:, None, :]
        all_anchors = np.reshape(all_anchors, [-1, 4])
        # first A rows correspond to A anchors of (0, 0) in feature map,
        # then (0, 1), (0, 2), ...
        return all_anchors

    def valid_flags(self, featmap_sizes, pad_shape, device="cuda"):
        """Generate valid flags of anchors in multiple feature levels

        Args:
            featmap_sizes (list(tuple)): List of feature map sizes in
                multiple feature levels.
            pad_shape (tuple): The padded shape of the image.
            device (str): Device where the anchors will be put on.

        Return:
            list(torch.Tensor): Valid flags of anchors in multiple levels.
        """
        assert self.num_levels == len(featmap_sizes)
        multi_level_flags = []
        for i in range(self.num_levels):
            anchor_stride = self.strides[i]
            feat_h, feat_w = featmap_sizes[i]
            h, w = pad_shape[:2]
            valid_feat_h = min(int(np.ceil(h / anchor_stride)), feat_h)
            valid_feat_w = min(int(np.ceil(w / anchor_stride)), feat_w)
            flags = self.single_level_valid_flags(
                (feat_h, feat_w),
                (valid_feat_h, valid_feat_w),
                self.num_base_anchors[i],
                device=device,
            )
            multi_level_flags.append(flags)
        return multi_level_flags

    # def single_level_valid_flags(
    #     self, featmap_size, valid_size, num_base_anchors, device="cuda"
    # ):
    #     feat_h, feat_w = featmap_size
    #     valid_h, valid_w = valid_size
    #     assert valid_h <= feat_h and valid_w <= feat_w
    #     valid_x = torch.zeros(feat_w, dtype=torch.uint8, device=device)
    #     valid_y = torch.zeros(feat_h, dtype=torch.uint8, device=device)
    #     valid_x[:valid_w] = 1
    #     valid_y[:valid_h] = 1
    #     valid_xx, valid_yy = self._meshgrid(valid_x, valid_y)
    #     valid = valid_xx & valid_yy
    #     valid = (
    #         valid[:, None].expand(valid.size(0), num_base_anchors).contiguous().view(-1)
    #     )
    #     return valid

    def __repr__(self):
        indent_str = "    "
        repr_str = self.__class__.__name__ + "(\n"
        repr_str += "{}strides={},\n".format(indent_str, self.strides)
        repr_str += "{}ratios={},\n".format(indent_str, self.ratios)
        repr_str += "{}scales={},\n".format(indent_str, self.scales)
        repr_str += "{}base_sizes={},\n".format(indent_str, self.base_sizes)
        repr_str += "{}scale_major={},\n".format(indent_str, self.scale_major)
        repr_str += "{}octave_base_scale={},\n".format(
            indent_str, self.octave_base_scale
        )
        repr_str += "{}scales_per_octave={},\n".format(
            indent_str, self.scales_per_octave
        )
        repr_str += "{}num_levels={}\n".format(indent_str, self.num_levels)
        repr_str += "{}centers={},\n".format(indent_str, self.centers)
        repr_str += "{}center_offset={})".format(indent_str, self.center_offset)
        return repr_str
