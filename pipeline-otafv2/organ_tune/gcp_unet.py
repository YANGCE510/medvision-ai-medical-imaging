import torch.nn as nn
from monai.networks.nets import UNet


class UNetForInference(nn.Module):
    def __init__(
        self,
        spatial_dims: int = 3,
        in_channels: int = 1,
        out_channels: int = 11,
        channels=(32, 64, 128, 256, 320, 320),
        strides=(2, 2, 2, 2, 2),
        num_res_units: int = 2,
        norm: str = "instance",
        act: str = "leakyrelu",
    ):
        super().__init__()
        self.unet = UNet(
            spatial_dims=spatial_dims,
            in_channels=in_channels,
            out_channels=out_channels,
            channels=channels,
            strides=strides,
            num_res_units=num_res_units,
            norm=norm,
            act=act,
        )

    def forward(self, x):
        return self.unet(x)


def build_unet_model(use_gcp: bool = True, out_channels: int = 11) -> nn.Module:
    return UNetForInference(
        spatial_dims=3,
        in_channels=1,
        out_channels=out_channels,
        channels=(32, 64, 128, 256, 320, 320),
        strides=(2, 2, 2, 2, 2),
        num_res_units=2,
        norm="instance",
        act="leakyrelu",
    )
