# Pipeline Colletting Data

## Collection 

1. Get the frame of camera
2. Automatic saving of image from camera (is like each X second save image)
3. Save manual the current frame of camera
4. List of folder where to save
5. Use a method for naming (like id_time)
6. Save depth frame (if is it possible)
7. Possibility to create a new folder 

### Comment

1. See the camera frame 
2. Define wich camera use to take photos


## Preprocess

1. Load a folder of images
2. Show the list image 
3. Have possibility to remove images from the folder
4. Augmentation (Possiblity to modify the photo)
5. Show current image


## Annotate

1. Load model
2. Use model for predict current image or all images in the folder
3. load folder of images
4. Possibility to create box, modify id of box, move, resize, delete
5. Possiblity to show the prediction of model in a different image, and have the possibility to confirm it 

## Training

1. load base model
2. possibility to chise the base model of yolo, selecting number version and size
3. Possiblity to modify the parameters of training
4. get statistics of training
5. possiblity to chose the name of results model
6. possibility to chose folders to use in the training in wich % 
7. possiblity to add class, or modify the base class

### Comment

1. How can have a models that can identify the object in a image

## Analisys 

1. Difference between models (some metrics precision, recall etc)
