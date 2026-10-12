"""
PPE Kit Model Custom Fine-Tuning and Evaluation Script
------------------------------------------------------
This reproducible script fine-tunes Ultralytics YOLOv8 on custom-labelled
PPE datasets (Roboflow PPE, Pictor PPE, or Kaggle Worker Safety dataset).

Usage:
  python train_model.py --data dataset.yaml --epochs 50 --batch 16
"""

import os
import argparse
from ultralytics import YOLO

def train_custom_ppe(data_yaml="data.yaml", epochs=30, batch_size=16, model_type="yolov8n.pt"):
    print("=" * 60)
    print("🚀 Initializing Ultralytics YOLO PPE Fine-Tuning Pipeline")
    print(f"📦 Base Model: {model_type}")
    print(f"📊 Dataset YAML: {data_yaml}")
    print(f"🔄 Epochs: {epochs} | Batch Size: {batch_size}")
    print("=" * 60)

    # 1. Load base model
    model = YOLO(model_type)

    # 2. Check if dataset YAML exists
    if not os.path.exists(data_yaml):
        print(f"⚠️ Dataset file '{data_yaml}' not found.")
        print("💡 Creating a template 'ppe_dataset_template.yaml' for guidance...")
        with open("ppe_dataset_template.yaml", "w") as f:
            f.write("""# PPE Detection Dataset Config
path: ./datasets/ppe_dataset # dataset root dir
train: images/train
val: images/val
test: images/test

# Classes:
names:
  0: person
  1: helmet
  2: vest
  3: goggles
  4: gloves
  5: mask
  6: boots
""")
        print("Template generated at: ppe_dataset_template.yaml")
        print("Download a dataset from Roboflow Universe (e.g. 'ppe-detection') and specify its data.yaml.")
        return

    # 3. Execute training
    print("🎯 Commencing training...")
    results = model.train(
        data=data_yaml,
        epochs=epochs,
        batch=batch_size,
        imgsz=640,
        plots=True,
        save=True,
        project="runs/ppe_training",
        name="ppe_yolov8"
    )

    print("\n✅ Fine-tuning completed!")
    best_weights = os.path.join("runs", "ppe_training", "ppe_yolov8", "weights", "best.pt")
    print(f"🏆 Best fine-tuned weights saved to: {best_weights}")
    print(f"To use these weights, copy to 'models/best.pt' and update MODEL_PATH in config.py")

    # 4. Evaluate metrics
    print("\n📊 Evaluating model on validation set...")
    metrics = model.val()
    print(f"mAP50: {metrics.box.map50:.4f}")
    print(f"mAP50-95: {metrics.box.map:.4f}")
    print(f"Precision: {metrics.box.mp:.4f}")
    print(f"Recall: {metrics.box.mr:.4f}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train custom YOLOv8 PPE Detection Model")
    parser.add_argument("--data", default="ppe_dataset_template.yaml", help="Path to data.yaml")
    parser.add_argument("--epochs", type=int, default=20, help="Number of training epochs")
    parser.add_argument("--batch", type=int, default=16, help="Batch size")
    parser.add_argument("--model", default="yolov8n.pt", help="Base model weights")
    args = parser.parse_args()

    train_custom_ppe(data_yaml=args.data, epochs=args.epochs, batch_size=args.batch, model_type=args.model)
