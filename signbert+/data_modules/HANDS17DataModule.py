import os

import numpy as np
import pandas as pd
import lightning.pytorch as pl
from torch.utils.data import DataLoader

from MaskKeypointDataset import MaskKeypointDataset, mask_keypoint_dataset_collate_fn
from IPython import embed; from sys import exit


class HANDS17DataModule(pl.LightningDataModule):
    HANDS17_DPATH = '/home/gts/projects/jsoutelo/SignBERT+/datasets/HANDS17'
    TRACKING_ANNOTATIONS_FPATH = os.path.join(HANDS17_DPATH, 'test', 'test_annotation_tracking.txt')
    PREPROCESS_DPATH = os.path.join(HANDS17_DPATH, 'preprocess')
    TRAIN_CSV_FPATH = os.path.join(PREPROCESS_DPATH, 'train.csv')
    TEST_CSV_FPATH = os.path.join(PREPROCESS_DPATH, 'test.csv')
    TRAIN_NPY_FPATH = os.path.join(PREPROCESS_DPATH, 'X_train.npy')
    TEST_NPY_FPATH = os.path.join(PREPROCESS_DPATH, 'X_test.npy')
    # World coordinates
    TRAIN_WC_NPY_FPATH = os.path.join(PREPROCESS_DPATH, 'wc_X_train.npy')
    TEST_WC_NPY_FPATH = os.path.join(PREPROCESS_DPATH, 'wc_X_test.npy')
    N_SEQUENCES = 99
    TRAIN_PCT = 0.7
    NUM_HAND_LANDMARKS = 21
    NUM_COORDINATES = 3
    # Parameters extracted fom `Camera info.txt`.
    INTRINSIC_CAM_PARAMS = np.array([
        [475.065948, 0, 315.944855],
        [0, 475.065857, 245.287079],
        [0, 0, 1]
    ])
    SEQ_PAD_VALUE = 0.0

    def __init__(self, batch_size):
        super().__init__()
        self.batch_size = batch_size

    def prepare_data(self):
        # Create preprocess directory if it does not exist
        if not os.path.isdir(HANDS17DataModule.PREPROCESS_DPATH):
            os.makedirs(HANDS17DataModule.PREPROCESS_DPATH)
        # Check if train/test CSV split exist, if not, create them
        if  not os.path.isfile(HANDS17DataModule.TRAIN_CSV_FPATH) or \
            not os.path.isfile(HANDS17DataModule.TEST_CSV_FPATH):

            train_df = pd.DataFrame()
            test_df = pd.DataFrame()
            df = pd.read_csv(
                HANDS17DataModule.TRACKING_ANNOTATIONS_FPATH, 
                sep='\t', 
                header=None
            )
            # Drop last column, all values are NaN
            df = df.iloc[:, :-1]
            for i in range(HANDS17DataModule.N_SEQUENCES):
                i += 1
                # Grab all frames from a sequence
                seq_df = df[df.iloc[:,0].str.contains(f'tracking\\{i}\\images',regex=False)]
                train_frames = int(len(seq_df) * HANDS17DataModule.TRAIN_PCT)
                # Split
                seq_train_df = seq_df[:train_frames]
                seq_test_df = seq_df[train_frames:]
                train_df = pd.concat([train_df, seq_train_df])
                test_df = pd.concat([test_df, seq_test_df])
            # Save CSV splits to disk
            train_df.to_csv(HANDS17DataModule.TRAIN_CSV_FPATH, index=False)
            test_df.to_csv(HANDS17DataModule.TEST_CSV_FPATH, index=False)
        # Check if train/test wc/uv Numpy array files exist, if not, create them
        if  not os.path.isfile(HANDS17DataModule.TRAIN_NPY_FPATH) or \
            not os.path.isfile(HANDS17DataModule.TEST_NPY_FPATH) or \
            not os.path.isfile(HANDS17DataModule.TRAIN_WC_NPY_FPATH) or \
            not os.path.isfile(HANDS17DataModule.TEST_WC_NPY_FPATH):
            
            # Load CSV splits
            train_df = pd.read_csv(HANDS17DataModule.TRAIN_CSV_FPATH)
            test_df = pd.read_csv(HANDS17DataModule.TEST_CSV_FPATH)

            wc_X_train = []
            wc_X_test = []
            X_train = []
            X_test = []
            for i in range(HANDS17DataModule.N_SEQUENCES):
                i += 1
                # Grab all frames from train/test split of the same sequence
                train_seq_df = train_df[train_df.iloc[:,0].str.contains(f'tracking\\{i}\\images', regex=False)]
                test_seq_df = test_df[test_df.iloc[:,0].str.contains(f'tracking\\{i}\\images', regex=False)]
                # Discard frame identifier column
                wc_X_train_seq = train_seq_df.iloc[:, 1:].to_numpy()
                wc_X_test_seq = test_seq_df.iloc[:, 1:].to_numpy()
                # Reshape array so we end up with (n_frames, n_kps, n_coords)
                wc_X_train_seq = wc_X_train_seq.reshape(
                    -1, 
                    HANDS17DataModule.NUM_HAND_LANDMARKS, 
                    HANDS17DataModule.NUM_COORDINATES
                )
                wc_X_test_seq = wc_X_test_seq.reshape(
                    -1, 
                    HANDS17DataModule.NUM_HAND_LANDMARKS, 
                    HANDS17DataModule.NUM_COORDINATES
                )
                # From XYZ world coordinates to UV pixel coordinates
                X_train_seq = self.from_wc_to_uv(wc_X_train_seq)
                X_test_seq = self.from_wc_to_uv(wc_X_test_seq)
                wc_X_train.append(wc_X_train_seq)
                wc_X_test.append(wc_X_test_seq)
                X_train.append(X_train_seq)
                X_test.append(X_test_seq)
            # Pad sequences
            X_train_max_len = max([len(seq) for seq in X_train])
            X_test_max_len = max([len(seq) for seq in X_test])
            for i in range(HANDS17DataModule.N_SEQUENCES):
                X_train_seq = X_train[i]
                X_test_seq = X_test[i]
                wc_X_train_seq = wc_X_train[i]
                wc_X_test_seq = wc_X_test[i]
                X_train_pad = ((0, X_train_max_len-len(X_train_seq)), (0,0), (0,0))
                X_test_pad = ((0, X_test_max_len-len(X_test_seq)), (0,0), (0,0))
                X_train_seq_pad = np.pad(
                    X_train_seq, 
                    X_train_pad, 
                    mode='constant', 
                    constant_values=HANDS17DataModule.SEQ_PAD_VALUE
                )
                wc_X_train_seq_pad = np.pad(
                    wc_X_train_seq, 
                    X_train_pad, 
                    mode='constant', 
                    constant_values=HANDS17DataModule.SEQ_PAD_VALUE
                )
                X_test_seq_pad = np.pad(
                    X_test_seq, 
                    X_test_pad, 
                    mode='constant', 
                    constant_values=HANDS17DataModule.SEQ_PAD_VALUE
                )
                wc_X_test_seq_pad = np.pad(
                    wc_X_test_seq, 
                    X_test_pad, 
                    mode='constant', 
                    constant_values=HANDS17DataModule.SEQ_PAD_VALUE
                )
                wc_X_train[i] = wc_X_train_seq_pad
                X_train[i] = X_train_seq_pad
                wc_X_test[i] = wc_X_test_seq_pad
                X_test[i] = X_test_seq_pad
            # Stack list of Numpy arrays together (n_seqs, n_frames, n_kps, n_coords)
            X_train = np.stack(X_train)
            X_test = np.stack(X_test)
            wc_X_train = np.stack(wc_X_train)
            wc_X_test = np.stack(wc_X_test)
            # Save to disk
            np.save(HANDS17DataModule.TRAIN_NPY_FPATH, X_train)
            np.save(HANDS17DataModule.TEST_NPY_FPATH, X_test)
            np.save(HANDS17DataModule.TRAIN_WC_NPY_FPATH, wc_X_train)
            np.save(HANDS17DataModule.TEST_WC_NPY_FPATH, wc_X_test)

    def from_wc_to_uv(self, wc):
        """Computes the UV pixel coordinates from the XYZ world coordinates."""
        uv = np.einsum('ij,nkj->nki', HANDS17DataModule.INTRINSIC_CAM_PARAMS, wc)
        uv = uv / uv[...,-1][...,None]
        uv = uv[..., :2]
        
        return uv

    def setup(self, stage=None):
        
        if stage == 'fit' or stage is None:
            self.setup_train = MaskKeypointDataset(HANDS17DataModule.TRAIN_NPY_FPATH)
            self.setup_test = MaskKeypointDataset(HANDS17DataModule.TEST_NPY_FPATH)

    def train_dataloader(self):
        return DataLoader(self.setup_train, batch_size=self.batch_size, collate_fn=mask_keypoint_dataset_collate_fn)

    def val_dataloader(self):
        return DataLoader(self.setup_test, batch_size=self.batch_size, collate_fn=mask_keypoint_dataset_collate_fn)


def create_keypoints_video_with_images(keypoints_array, rgb_images, output_file, frame_rate=30, point_radius=3):
    """
    Create a video showcasing the coordinates of keypoints overlaid on RGB images.

    Parameters:
        keypoints_array (numpy.ndarray): The input 3D array representing frames, key point types, and xy coordinates.
        rgb_images (List[numpy.ndarray]): List of RGB images corresponding to the keypoint sequences.
        output_file (str): The output video file path (e.g., 'output.mp4').
        frame_rate (int): The frame rate of the output video (default is 30 fps).
        point_radius (int): The radius of the key points to be drawn on each frame (default is 3).

    Returns:
        None
    """
    num_frames, num_keypoints, _ = keypoints_array.shape
    frame_height, frame_width, _ = rgb_images[0].shape

    # Create a VideoWriter object to save the output video
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_file, fourcc, frame_rate, (frame_width, frame_height))

    for frame_index in range(num_frames):
        frame = rgb_images[frame_index].copy()  # Copy the RGB image to avoid modifying the original

        for kp_index in range(num_keypoints):
            x, y = keypoints_array[frame_index, kp_index]
            # Draw a circle for each key point type
            color = (0, 0, 255)  # Red color (BGR format)
            cv2.circle(frame, (int(x), int(y)), point_radius, color, -1)

        # Write the frame to the output video
        out.write(frame)

    # Release the VideoWriter and close the video file
    out.release()

if __name__ == '__main__':
    import cv2

    dataset = HANDS17DataModule(batch_size=32)
    dataset.prepare_data()

    # test
    X_train = np.load(dataset.TRAIN_NPY_FPATH)
    tracking_imgs_dpath = '/home/gts/projects/jsoutelo/SignBERT+/datasets/HANDS17/tracking'
    # grab a random sample
    sample_idx = np.random.choice(len(X_train))
    random_sample = X_train[sample_idx]
    # remove paddings
    random_sample = random_sample[(random_sample != 0.0).all((1,2))]
    # grab tracking images
    tracking_imgs_dpath = os.path.join(tracking_imgs_dpath, str(sample_idx + 1), 'images')
    num_frames = len(random_sample)
    tracking_imgs = sorted(os.listdir(tracking_imgs_dpath))[:num_frames]
    tracking_imgs = [os.path.join(tracking_imgs_dpath, ti) for ti in tracking_imgs]
    tracking_imgs = [cv2.imread(ti, cv2.IMREAD_UNCHANGED) for ti in tracking_imgs]
    tracking_imgs = [cv2.normalize(ti, dst=None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_8UC1) for ti in tracking_imgs]
    tracking_imgs = [cv2.applyColorMap(ti, cv2.COLORMAP_BONE) for ti in tracking_imgs]
    
    create_keypoints_video_with_images(
        random_sample, 
        tracking_imgs, 
        './visualizations/test_hands17_random_sample_data_module.mp4'
    )

    embed(); exit()
