/** One sample's ICP-OES reading: non-null fixed elements only, ppm. Returned by
 *  GET /core-floods/{base_id}/icp and GET /experiments/{experiment_id}/icp. */
export interface IcpRow {
  result_id: number
  experiment_id: string
  is_variant: boolean
  cumulative_time_post_reaction_days: number | null
  sample_date: string | null
  elements: Record<string, number>
}

/** First cumulative day of a chained segment, drawn as a chart marker. */
export interface IcpSegmentStart {
  experiment_id: string
  day: number
}

/** Body of GET /experiments/{experiment_id}/icp: the experiment's whole series. */
export interface ExperimentIcp {
  rows: IcpRow[]
  segment_starts: IcpSegmentStart[]
}
