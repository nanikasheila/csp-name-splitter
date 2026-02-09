from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import Config
from .errors import ConfigError, ImageReadError, LimitExceededError
from .job import CancelToken, JobResult, ProgressEvent, run_job


@dataclass(frozen=True)
class BatchJobSpec:
    # バッチ処理の1ジョブ仕様
    input_image: Path
    config: Config
    out_dir: Path | None = None


@dataclass(frozen=True)
class BatchProgress:
    # バッチ全体の進捗
    current_job: int
    total_jobs: int
    job_name: str
    job_progress: ProgressEvent | None = None


@dataclass(frozen=True)
class BatchJobResult:
    # 1ジョブの実行結果
    input_image: Path
    success: bool
    result: JobResult | None = None
    error: Exception | None = None


@dataclass(frozen=True)
class BatchResult:
    # バッチ全体の実行結果
    total_jobs: int
    successful_jobs: int
    failed_jobs: int
    results: list[BatchJobResult]


def find_images_in_directory(directory: Path, recursive: bool = False) -> list[Path]:
    """ディレクトリ内のPNG画像を検索"""
    if recursive:
        images = list(directory.glob("**/*.png"))
    else:
        images = list(directory.glob("*.png"))
    return sorted(images)


def find_config_for_image(image_path: Path, default_config: Config) -> Config:
    """画像に対応する設定ファイルを検索
    
    検索順序:
    1. <image_name>_config.yaml (例: page001.png → page001_config.yaml)
    2. <image_name>.yaml (例: page001.png → page001.yaml)
    3. デフォルト設定
    """
    # 同名の設定ファイル（_config.yaml）
    config_path = image_path.with_suffix("").with_suffix(".yaml")
    alt_config_path = image_path.parent / f"{image_path.stem}_config.yaml"
    
    for path in [alt_config_path, config_path]:
        if path.exists():
            try:
                from .config import load_config
                return load_config(path)
            except ConfigError:
                # 設定ファイルが不正な場合はデフォルトにフォールバック
                pass
    
    return default_config


def run_batch(
    job_specs: list[BatchJobSpec],
    *,
    on_progress: Callable[[BatchProgress], None] | None = None,
    cancel_token: CancelToken | None = None,
) -> BatchResult:
    """バッチ処理を実行
    
    Args:
        job_specs: ジョブ仕様のリスト
        on_progress: 進捗コールバック
        cancel_token: キャンセルトークン
        
    Returns:
        バッチ実行結果
    """
    results: list[BatchJobResult] = []
    total_jobs = len(job_specs)
    
    for index, spec in enumerate(job_specs, start=1):
        # キャンセルチェック
        if cancel_token and cancel_token.cancelled:
            # 残りのジョブを失敗として記録
            for remaining_spec in job_specs[index - 1:]:
                results.append(
                    BatchJobResult(
                        input_image=remaining_spec.input_image,
                        success=False,
                        error=RuntimeError("Batch cancelled"),
                    )
                )
            break
        
        # バッチ進捗通知
        if on_progress:
            on_progress(
                BatchProgress(
                    current_job=index,
                    total_jobs=total_jobs,
                    job_name=spec.input_image.name,
                    job_progress=None,
                )
            )
        
        # ジョブ進捗コールバック
        def job_progress_callback(event: ProgressEvent) -> None:
            if on_progress:
                on_progress(
                    BatchProgress(
                        current_job=index,
                        total_jobs=total_jobs,
                        job_name=spec.input_image.name,
                        job_progress=event,
                    )
                )
        
        # ジョブ実行
        try:
            result = run_job(
                str(spec.input_image),
                spec.config,
                out_dir=str(spec.out_dir) if spec.out_dir else None,
                on_progress=job_progress_callback,
                cancel_token=cancel_token,
            )
            results.append(
                BatchJobResult(
                    input_image=spec.input_image,
                    success=True,
                    result=result,
                )
            )
        except (ConfigError, LimitExceededError, ImageReadError, ValueError, RuntimeError) as exc:
            results.append(
                BatchJobResult(
                    input_image=spec.input_image,
                    success=False,
                    error=exc,
                )
            )
    
    # 結果集計
    successful_jobs = sum(1 for r in results if r.success)
    failed_jobs = sum(1 for r in results if not r.success)
    
    return BatchResult(
        total_jobs=total_jobs,
        successful_jobs=successful_jobs,
        failed_jobs=failed_jobs,
        results=results,
    )


def prepare_batch_jobs(
    paths: list[Path],
    default_config: Config,
    *,
    recursive: bool = False,
    auto_config: bool = True,
) -> list[BatchJobSpec]:
    """パスのリストからバッチジョブ仕様を準備
    
    Args:
        paths: 画像ファイルまたはディレクトリのパス
        default_config: デフォルト設定
        recursive: ディレクトリを再帰的に探索するか
        auto_config: 画像ごとに設定ファイルを自動検索するか
        
    Returns:
        ジョブ仕様のリスト
    """
    job_specs: list[BatchJobSpec] = []
    
    for path in paths:
        if path.is_dir():
            # ディレクトリの場合: 内部の画像を検索
            images = find_images_in_directory(path, recursive=recursive)
            for image in images:
                config = find_config_for_image(image, default_config) if auto_config else default_config
                # 出力先はデフォルト（画像パスから自動決定）
                job_specs.append(BatchJobSpec(input_image=image, config=config))
        elif path.is_file() and path.suffix.lower() == ".png":
            # PNG画像の場合
            config = find_config_for_image(path, default_config) if auto_config else default_config
            job_specs.append(BatchJobSpec(input_image=path, config=config))
    
    return job_specs


__all__ = [
    "BatchJobSpec",
    "BatchProgress",
    "BatchJobResult",
    "BatchResult",
    "find_images_in_directory",
    "find_config_for_image",
    "run_batch",
    "prepare_batch_jobs",
]
