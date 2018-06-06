# -*- coding: utf-8 -*-
import uuid
from pathlib import Path

from celery import shared_task

from grandchallenge.algorithms.models import Job, Result
from grandchallenge.evaluation.backends.dockermachine.evaluator import \
    Evaluator
from grandchallenge.evaluation.backends.dockermachine.utils import cleanup, \
    put_file
from grandchallenge.evaluation.exceptions import SubmissionError


class AlgorithmExecutor(Evaluator):
    def __init__(self, *args, input_files, **kwargs):
        super().__init__(*args,
                         input_file=None,
                         results_file=Path("/output/results.json"),
                         **kwargs)
        self._input_files = input_files

    def _provision_input_volume(self):
        try:
            with cleanup(
                    self._client.containers.run(
                        image=self._io_image,
                        volumes={
                            self._input_volume: {
                                'bind': '/input/', 'mode': 'rw'
                            }
                        },
                        detach=True,
                        tty=True,
                        **self._run_kwargs,
                    )
            ) as writer:

                for case in self._input_files:
                    dest_file = f"/input/{Path(case.name).name}"
                    put_file(
                        container=writer, src=case, dest=dest_file
                    )

        except Exception as exc:
            raise SubmissionError(str(exc))


@shared_task
def execute_algorithm(*, job_pk: uuid.UUID):
    # TODO: error handling

    job = Job.objects.get(pk=job_pk)

    job.update_status(status=Job.STARTED)

    try:
        with AlgorithmExecutor(
                job_id=job_pk,
                input_files=[c.file for c in job.case.casefile_set.all()],
                eval_image=job.algorithm.image,
                eval_image_sha256=job.algorithm.image_sha256,
        ) as e:
            result = e.evaluate()
    except Exception as e:
        job.update_status(status=job.FAILURE, output=str(e))
        return

    Result.objects.create(job=job, output=result)
    job.update_status(status=Job.SUCCESS)
